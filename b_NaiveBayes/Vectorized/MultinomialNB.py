import matplotlib.pyplot as plt

from b_NaiveBayes.Vectorized.Basic import *
from Util import DataUtil


class MultinomialNB(NaiveBayes):

    def feed_data(self, x, y, sample_weights=None):
        x, y, features, feat_dics, label_dic = DataUtil.quantize_data(x, y)
        cat_counter = np.bincount(y)
        n_possibilities = [len(feats) for feats in features]

        labels = [y == value for value in range(len(cat_counter))]
        labelled_x = [x[ci].T for ci in labels]

        self._x, self._y = x, y
        self._labelled_x, self._label_zip = labelled_x, list(zip(labels, labelled_x))
        self._cat_counter, self._feat_dics, self._n_possibilities = cat_counter, feat_dics, n_possibilities
        self.label_dic = {i: _l for _l, i in label_dic.items()}
        self.feed_sample_weights(sample_weights)

    def feed_sample_weights(self, sample_weights=None):
        self._con_counter = []
        for dim, _p in enumerate(self._n_possibilities):
            if sample_weights is None:
                self._con_counter.append([
                    np.bincount(xx[dim], minlength=_p) for xx in self._labelled_x])
            else:
                self._con_counter.append([
                    np.bincount(xx[dim], weights=sample_weights[label] / sample_weights[label].mean(), minlength=_p)
                    for label, xx in self._label_zip])

    def _fit(self, lb):
        lb = 0
        n_dim = len(self._n_possibilities)
        n_category = len(self._cat_counter)
        p_category = self.get_prior_probability(lb)

        data = [None] * n_dim
        for dim, n_possibilities in enumerate(self._n_possibilities):
            data[dim] = [
                [(self._con_counter[dim][c][p] + lb) / (self._cat_counter[c] + lb * n_possibilities)
                 for p in range(n_possibilities)] for c in range(n_category)]
        self._data = [np.array(dim_info) for dim_info in data]

        def func(input_x, tar_category):
            input_x = np.atleast_2d(input_x).T
            rs = np.ones(input_x.shape[1])
            for d, xx in enumerate(input_x):
                rs *= self._data[d][tar_category][xx]
            return rs * p_category[tar_category]

        return func

    def _transfer_x(self, x):
        for i, line in enumerate(x):
            for j, char in enumerate(line):
                x[i][j] = self._feat_dics[j][char]
        return x

    def visualize(self, save=False):
        colors = plt.cm.Paired([i / len(self.label_dic) for i in range(len(self.label_dic))])
        colors = {_cat: _color for _cat, _color in zip(self.label_dic.values(), colors)}
        _rev_feat_dics = [{_val: _key for _key, _val in _feat_dic.items()} for _feat_dic in self._feat_dics]
        for j in range(len(self._n_possibilities)):
            _rev_dic = _rev_feat_dics[j]
            sj = self._n_possibilities[j]
            tmp_x = np.arange(1, sj + 1)
            title = "$j = {}; S_j = {}$".format(j + 1, sj)
            plt.figure()
            plt.title(title)
            for c in range(len(self.label_dic)):
                plt.bar(tmp_x - 0.35 * c, self._data[j][c, :], width=0.35,
                        facecolor=colors[self.label_dic[c]], edgecolor="white",
                        label=u"class: {}".format(self.label_dic[c]))
            plt.xticks([i for i in range(sj + 2)], [""] + [_rev_dic[i] for i in range(sj)] + [""])
            plt.ylim(0, 1.0)
            plt.legend()
            if not save:
                plt.show()
            else:
                plt.savefig("d{}".format(j + 1))

if __name__ == '__main__':
    import time

    _data = DataUtil.get_dataset("mushroom", "../../_Data/mushroom.txt")
    np.random.shuffle(_data)
    train_num = 6000
    train_x = _data[:train_num]
    test_x = _data[train_num:]
    train_y = [xx.pop(0) for xx in train_x]
    test_y = [xx.pop(0) for xx in test_x]
    learning_time = time.time()
    nb = MultinomialNB()
    nb.fit(train_x, train_y)
    learning_time = time.time() - learning_time
    estimation_time = time.time()
    nb.estimate(train_x, train_y)
    nb.estimate(test_x, test_y)
    estimation_time = time.time() - estimation_time
    print(
        "Model building  : {:12.6} s\n"
        "Estimation      : {:12.6} s\n"
        "Total           : {:12.6} s".format(
            learning_time, estimation_time,
            learning_time + estimation_time
        )
    )
    nb.visualize()
