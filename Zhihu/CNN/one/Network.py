import matplotlib.pyplot as plt

from Zhihu.CNN.Layers import *
from Zhihu.CNN.Optimizers import *
from Zhihu.CNN.Util import ProgressBar

np.random.seed(142857)  # for reproducibility


class NNVerbose:
    NONE = 0
    EPOCH = 1
    METRICS = 2
    METRICS_DETAIL = 3
    DETAIL = 4
    DEBUG = 5


# Neural Network

class NNBase:
    NNTiming = Timing()

    def __init__(self):
        self._layers = []
        self._optimizer = None
        self._current_dimension = 0

        self._tfx = self._tfy = None
        self._tf_weights, self._tf_bias = [], []
        self._cost = self._y_pred = None

        self._train_step = None
        self.verbose = 0

    def __str__(self):
        return "Neural Network"

    __repr__ = __str__

    def feed_timing(self, timing):
        if isinstance(timing, Timing):
            self.NNTiming = timing
            for layer in self._layers:
                layer.feed_timing(timing)

    @staticmethod
    def _get_w(shape):
        initial = tf.truncated_normal(shape, stddev=0.1)
        return tf.Variable(initial, name="w")

    @staticmethod
    def _get_b(shape):
        initial = tf.constant(0.1, shape=shape)
        return tf.Variable(initial, name="b")

    def _add_weight(self, shape, conv_channel=None, fc_shape=None):
        if fc_shape is not None:
            w_shape = (fc_shape, shape[1])
            b_shape = shape[1],
        elif conv_channel is not None:
            if len(shape[1]) <= 2:
                w_shape = shape[1][0], shape[1][1], conv_channel, conv_channel
            else:
                w_shape = (shape[1][1], shape[1][2], conv_channel, shape[1][0])
            b_shape = shape[1][0],
        else:
            w_shape = shape
            b_shape = shape[1],
        self._tf_weights.append(self._get_w(w_shape))
        self._tf_bias.append(self._get_b(b_shape))

    @NNTiming.timeit(level=1, prefix="[API] ")
    def get_rs(self, x, y=None):
        _cache = self._layers[0].activate(x, self._tf_weights[0], self._tf_bias[0])
        for i, layer in enumerate(self._layers[1:]):
            if i == len(self._layers) - 2:
                if isinstance(self._layers[i], ConvLayer):
                    _cache = tf.reshape(_cache, [-1, int(np.prod(_cache.get_shape()[1:]))])
                if y is None:
                    return tf.matmul(_cache, self._tf_weights[-1]) + self._tf_bias[-1]
                return layer.activate(_cache, self._tf_weights[i + 1], self._tf_bias[i + 1], y)
            _cache = layer.activate(_cache, self._tf_weights[i + 1], self._tf_bias[i + 1])
        return _cache

    def add(self, layer):
        if not self._layers:
            self._layers, self._current_dimension = [layer], layer.shape[1]
            if isinstance(layer, ConvLayer):
                self._add_weight(layer.shape, layer.n_channels)
            else:
                self._add_weight(layer.shape)
        else:
            if len(layer.shape) == 2:
                _current, _next = layer.shape
            elif len(layer.shape) == 1:
                _next = layer.shape[0]
                layer.shape = (self._current_dimension, _next)
                _current = self._current_dimension
            else:
                raise ValueError
            fc_shape, conv_channel, last_layer = None, None, self._layers[-1]
            if isinstance(last_layer, ConvLayer):
                if isinstance(layer, ConvLayer):
                    conv_channel = last_layer.n_filters
                    _current = (conv_channel, last_layer.out_h, last_layer.out_w)
                    layer.feed_shape((_current, _next))
                else:
                    layer.is_fc = True
                    last_layer.is_fc_base = True
                    fc_shape = last_layer.out_h * last_layer.out_w * last_layer.n_filters
            self._layers.append(layer)
            self._add_weight((_current, _next), conv_channel, fc_shape)
            self._current_dimension = _next


class NNDist(NNBase):
    NNTiming = Timing()

    def __init__(self):
        NNBase.__init__(self)
        self._logs = {}
        self._sess = tf.Session()
        self._metrics, self._metric_names = [], []
        self._available_metrics = {
            "acc": NNDist._acc, "_acc": NNDist._acc,
            "f1_score": NNDist._f1_score, "_f1_score": NNDist._f1_score
        }

    # Utils

    @staticmethod
    @NNTiming.timeit(level=4, prefix="[Private StaticMethod] ")
    def _transfer_x(x):
        if len(x.shape) == 1:
            x = x.reshape(1, -1)
        if len(x.shape) == 4:
            x = x.transpose(0, 2, 3, 1)
        return x.astype(np.float32)

    @NNTiming.timeit(level=2)
    def _get_prediction(self, x, name=None, batch_size=1e6, verbose=None, out_of_sess=False):
        if verbose is None:
            verbose = self.verbose
        single_batch = int(batch_size / np.prod(x.shape[1:]))
        if not single_batch:
            single_batch = 1
        if single_batch >= len(x):
            if not out_of_sess:
                return self._y_pred.eval(feed_dict={self._tfx: x})
            with self._sess.as_default():
                x = x.astype(np.float32)
                return self.get_rs(x).eval(feed_dict={self._tfx: x})
        epoch = int(len(x) / single_batch)
        if not len(x) % single_batch:
            epoch += 1
        name = "Prediction" if name is None else "Prediction ({})".format(name)
        sub_bar = ProgressBar(min_value=0, max_value=epoch, name=name)
        if verbose >= NNVerbose.METRICS:
            sub_bar.start()
        if not out_of_sess:
            rs = [self._y_pred.eval(feed_dict={self._tfx: x[:single_batch]})]
        else:
            rs = [self.get_rs(x[:single_batch])]
        count = single_batch
        if verbose >= NNVerbose.METRICS:
            sub_bar.update()
        while count < len(x):
            count += single_batch
            if count >= len(x):
                if not out_of_sess:
                    rs.append(self._y_pred.eval(feed_dict={self._tfx: x[count - single_batch:]}))
                else:
                    rs.append(self.get_rs(x[count - single_batch:]))
            else:
                if not out_of_sess:
                    rs.append(self._y_pred.eval(feed_dict={self._tfx: x[count - single_batch:count]}))
                else:
                    rs.append(self.get_rs(x[count - single_batch:count]))
            if verbose >= NNVerbose.METRICS:
                sub_bar.update()
        if out_of_sess:
            with self._sess.as_default():
                rs = [_rs.eval() for _rs in rs]
        return np.vstack(rs)

    @NNTiming.timeit(level=3)
    def _append_log(self, x, y, name, out_of_sess=False):
        y_pred = self._get_prediction(x, name, out_of_sess=out_of_sess)
        for i, metric in enumerate(self._metrics):
            self._logs[name][i].append(metric(y, y_pred))
        if not out_of_sess:
            self._logs[name][-1].append(self._layers[-1].calculate(y, y_pred).eval())
        else:
            with self._sess.as_default():
                self._logs[name][-1].append(self._layers[-1].calculate(y, y_pred).eval())

    @NNTiming.timeit(level=3)
    def _print_metric_logs(self, data_type):
        print()
        print("=" * 47)
        for i, name in enumerate(self._metric_names):
            print("{:<16s} {:<16s}: {:12.8}".format(
                data_type, name, self._logs[data_type][i][-1]))
        print("{:<16s} {:<16s}: {:12.8}".format(
            data_type, "loss", self._logs[data_type][-1][-1]))
        print("=" * 47)

    # Metrics

    @staticmethod
    @NNTiming.timeit(level=2, prefix="[Private StaticMethod] ")
    def _acc(y, y_pred):
        y_arg, y_pred_arg = np.argmax(y, axis=1), np.argmax(y_pred, axis=1)
        return np.sum(y_arg == y_pred_arg) / len(y_arg)

    @staticmethod
    @NNTiming.timeit(level=2, prefix="[Private StaticMethod] ")
    def _f1_score(y, y_pred):
        y_true, y_pred = np.argmax(y, axis=1), np.argmax(y_pred, axis=1)
        tp = np.sum(y_true * y_pred)
        if tp == 0:
            return .0
        fp = np.sum((1 - y_true) * y_pred)
        fn = np.sum(y_true * (1 - y_pred))
        return 2 * tp / (2 * tp + fn + fp)

    # API

    @NNTiming.timeit(level=1, prefix="[API] ")
    def fit(self, x=None, y=None, lr=0.01, epoch=10, batch_size=128, train_rate=None,
            verbose=0, metrics=None, record_period=100):

        self.verbose = verbose
        x = NNDist._transfer_x(x)
        self._optimizer = Adam(lr)
        self._tfx = tf.placeholder(tf.float32, shape=[None, *x.shape[1:]])
        self._tfy = tf.placeholder(tf.float32, shape=[None, y.shape[1]])

        if train_rate is not None:
            train_rate = float(train_rate)
            train_len = int(len(x) * train_rate)
            shuffle_suffix = np.random.permutation(int(len(x)))
            x, y = x[shuffle_suffix], y[shuffle_suffix]
            x_train, y_train = x[:train_len], y[:train_len]
            x_test, y_test = x[train_len:], y[train_len:]
        else:
            x_train = x_test = x
            y_train = y_test = y

        train_len = len(x_train)
        batch_size = min(batch_size, train_len)
        do_random_batch = train_len >= batch_size
        train_repeat = int(train_len / batch_size) + 1

        self._metrics = ["acc"] if metrics is None else metrics
        for i, metric in enumerate(self._metrics):
            if isinstance(metric, str):
                self._metrics[i] = self._available_metrics[metric]
        self._metric_names = [_m.__name__ for _m in self._metrics]
        self._logs = {
            name: [[] for _ in range(len(self._metrics) + 1)] for name in ("train", "test")
        }

        bar = ProgressBar(min_value=0, max_value=max(1, epoch // record_period), name="Epoch")
        if self.verbose >= NNVerbose.EPOCH:
            bar.start()

        with self._sess.as_default() as sess:

            # Define session
            self._cost = self.get_rs(self._tfx, self._tfy)
            self._y_pred = self.get_rs(self._tfx)
            self._train_step = self._optimizer.minimize(self._cost)
            sess.run(tf.global_variables_initializer())

            # Train
            sub_bar = ProgressBar(min_value=0, max_value=train_repeat * record_period - 1, name="Iteration")
            for counter in range(epoch):
                if self.verbose >= NNVerbose.EPOCH and counter % record_period == 0:
                    sub_bar.start()
                for _i in range(train_repeat):
                    if do_random_batch:
                        batch = np.random.choice(train_len, batch_size)
                        x_batch, y_batch = x_train[batch], y_train[batch]
                    else:
                        x_batch, y_batch = x_train, y_train
                    self._train_step.run(feed_dict={self._tfx: x_batch, self._tfy: y_batch})
                    if self.verbose >= NNVerbose.EPOCH:
                        if sub_bar.update() and self.verbose >= NNVerbose.METRICS_DETAIL:
                            self._append_log(x_train, y_train, "train")
                            self._append_log(x_test, y_test, "test")
                            self._print_metric_logs("train")
                            self._print_metric_logs("test")
                if self.verbose >= NNVerbose.EPOCH:
                    sub_bar.update()
                if (counter + 1) % record_period == 0:
                    self._append_log(x_train, y_train, "train")
                    self._append_log(x_test, y_test, "test")
                    if self.verbose >= NNVerbose.METRICS:
                        self._print_metric_logs("train")
                        self._print_metric_logs("test")
                    if self.verbose >= NNVerbose.EPOCH:
                        bar.update(counter // record_period + 1)
                        sub_bar = ProgressBar(min_value=0, max_value=train_repeat * record_period - 1, name="Iteration")

    def draw_logs(self):
        metrics_log, loss_log = {}, {}
        for key, value in sorted(self._logs.items()):
            metrics_log[key], loss_log[key] = value[:-1], value[-1]
        for i, name in enumerate(sorted(self._metric_names)):
            plt.figure()
            plt.title("Metric Type: {}".format(name))
            for key, log in sorted(metrics_log.items()):
                xs = np.arange(len(log[i])) + 1
                plt.plot(xs, log[i], label="Data Type: {}".format(key))
            plt.legend(loc=4)
            plt.show()
            plt.close()
        plt.figure()
        plt.title("Loss")
        for key, loss in sorted(loss_log.items()):
            xs = np.arange(len(loss)) + 1
            plt.plot(xs, loss, label="Data Type: {}".format(key))
        plt.legend()
        plt.show()
