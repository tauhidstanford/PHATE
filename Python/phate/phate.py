"""
Potential of Heat-diffusion for Affinity-based Trajectory Embedding (PHATE)
"""

# author: Daniel Burkhardt <daniel.burkhardt@yale.edu>
# (C) 2017 Krishnaswamy Lab GPLv2

import time
import numpy as np
import sys
from sklearn.base import BaseEstimator
from sklearn.exceptions import NotFittedError
from scipy.spatial.distance import pdist
from scipy.spatial.distance import squareform
from scipy.linalg import svd

from .mds import embed_MDS


def calculate_kernel(M, a=10, k=5, knn_dist='euclidean', verbose=True):
    if verbose:
        print("Building kNN graph and diffusion operator...")
    try:
        pdx = squareform(pdist(M, metric=knn_dist))
        knn_dist = np.sort(pdx, axis=1)
        # bandwidth(x) = distance to k-th neighbor of x
        epsilon = knn_dist[:, k]
        pdx = (pdx / epsilon).T  # autotuning d(x,:) using epsilon(x).
    except RuntimeWarning:
        raise ValueError(
            'It looks like you have at least k identical data points. '
            'Try removing duplicates.')

    gs_ker = np.exp(-1 * (pdx ** a))  # not really Gaussian kernel
    gs_ker = gs_ker + gs_ker.T  # symmetrization
    return gs_ker


def calculate_operator(data, a=10, k=5, knn_dist='euclidean',
                       gs_ker=None, diff_op=None,
                       njobs=1, verbose=True):
    """
    Calculate the diffusion operator

    Parameters
    ----------
    data : ndarray [n, p]
        2 dimensional input data array with n cells and p dimensions

    a : int, optional, default: 10
        sets decay rate of kernel tails

    k : int, optional, default: 5
        used to set epsilon while autotuning kernel bandwidth

    knn_dist : string, optional, default: 'euclidean'
        recommended values: 'euclidean' and 'cosine'
        Any metric from scipy.spatial.distance can be used
        distance metric for building kNN graph

    gs_ker : array-like, shape [n_samples, n_samples]
        Precomputed graph kernel

    diff_op : ndarray, optional [n, n], default: None
        Precomputed diffusion operator

    verbose : boolean, optional, default: True
        Print updates during PHATE embedding

    Returns
    -------
    gs_ker : array-like, shape [n_samples, n_samples]
        The graph kernel built on the input data
        Only necessary for calculating Von Neumann Entropy

    diff_op : array-like, shape [n_samples, n_samples]
        The diffusion operator fit on the input data
    """
    # print('Imported numpy: %s'%np.__file__)

    tic = time.time()
    if gs_ker is None:
        diff_op = None  # can't use precomputed operator
        gs_ker = calculate_kernel(data, a, k, knn_dist, verbose=verbose)
    if diff_op is None:
        diff_op = gs_ker / gs_ker.sum(axis=1)[:, None]  # row stochastic
        if verbose:
            print("Built graph and diffusion operator in %.2f seconds." %
                  (time.time() - tic))
    else:
        if verbose:
            print("Using precomputed diffusion operator...")

    return gs_ker, diff_op


def embed_mds(diff_op, t=30, n_components=2, diff_potential=None,
              embedding=None, mds='metric', mds_dist='euclidean', njobs=1,
              random_state=None, verbose=True):
    """
    Create the MDS embedding from the diffusion potential

    Parameters
    ----------

    diff_op : array-like, shape [n_samples, n_samples]
        The diffusion operator fit on the input data

    t : int, optional, default: 30
        power to which the diffusion operator is powered
        sets the level of diffusion

    n_components : int, optional, default: 2
        number of dimensions in which the data will be embedded

    diff_potential : ndarray, optional [n, n], default: None
        Precomputed diffusion potential

    mds : string, optional, default: 'metric'
        choose from ['classic', 'metric', 'nonmetric']
        which multidimensional scaling algorithm is used for dimensionality
        reduction

    mds_dist : string, optional, default: 'euclidean'
        recommended values: 'euclidean' and 'cosine'
        Any metric from scipy.spatial.distance can be used
        distance metric for MDS

    random_state : integer or numpy.RandomState, optional
        The generator used to initialize SMACOF (metric, nonmetric) MDS
        If an integer is given, it fixes the seed
        Defaults to the global numpy random number generator

    verbose : boolean, optional, default: True
        Print updates during PHATE embedding

    Returns
    -------

    diff_potential : array-like, shape [n_samples, n_samples]
        Precomputed diffusion potential

    embedding : ndarray [n_samples, n_components]
        PHATE embedding in low dimensional space.
    """

    if diff_potential is None:
        embedding = None  # can't use precomputed embedding
        tic = time.time()
        if verbose:
            print("Calculating diffusion potential...")
        # transforming X
        # print('Diffusion operator • %s:'%t)
        # print(diff_op)
        X = np.linalg.matrix_power(diff_op, t)  # diffused diffusion operator
        # print('X:')
        # print(X)
        X[X == 0] = np.finfo(float).eps  # handling zeros
        X[X <= np.finfo(float).eps] = np.finfo(
            float).eps  # handling small values
        diff_potential = -1 * np.log(X)  # diffusion potential
        if verbose:
            print("Calculated diffusion potential in %.2f seconds." %
                  (time.time() - tic))
    # if diffusion potential is precomputed (i.e. 'mds' or 'mds_dist' has
    # changed on PHATE object)
    else:
        if verbose:
            print("Using precomputed diffusion potential...")

    tic = time.time()
    if verbose:
        print("Embedding data using %s MDS..." % (mds))
    if embedding is None:
        embedding = embed_MDS(diff_potential, ndim=n_components, how=mds,
                              distance_metric=mds_dist, njobs=njobs,
                              seed=random_state)
        if verbose:
            print("Embedded data in %.2f seconds." % (time.time() - tic))
    else:
        if verbose:
            print("Using precomputed embedding...")
    return embedding, diff_potential


class PHATE(BaseEstimator):
    """Potential of Heat-diffusion for Affinity-based Trajectory Embedding (PHATE)
    Embeds high dimensional single-cell data into two or three dimensions for
    visualization of biological progressions.

    Parameters
    ----------
    data : ndarray [n, p]
        2 dimensional input data array with n cells and p dimensions

    n_components : int, optional, default: 2
        number of dimensions in which the data will be embedded

    a : int, optional, default: 10
        sets decay rate of kernel tails

    k : int, optional, default: 5
        used to set epsilon while autotuning kernel bandwidth

    t : int, optional, default: 30
        power to which the diffusion operator is powered
        sets the level of diffusion

    mds : string, optional, default: 'metric'
        choose from ['classic', 'metric', 'nonmetric']
        which MDS algorithm is used for dimensionality reduction

    knn_dist : string, optional, default: 'euclidean'
        recommended values: 'euclidean' and 'cosine'
        Any metric from scipy.spatial.distance can be used
        distance metric for building kNN graph

    mds_dist : string, optional, default: 'euclidean'
        recommended values: 'euclidean' and 'cosine'
        Any metric from scipy.spatial.distance can be used
        distance metric for MDS

    njobs : integer, optional, default: 1
        The number of jobs to use for the computation.
        If -1 all CPUs are used. If 1 is given, no parallel computing code is
        used at all, which is useful for debugging.
        For n_jobs below -1, (n_cpus + 1 + n_jobs) are used. Thus for
        n_jobs = -2, all CPUs but one are used

    random_state : integer or numpy.RandomState, optional
        The generator used to initialize SMACOF (metric, nonmetric) MDS
        If an integer is given, it fixes the seed
        Defaults to the global numpy random number generator

    Attributes
    ----------

    embedding : array-like, shape [n_samples, n_dimensions]
        Stores the position of the dataset in the embedding space

    gs_ker : array-like, shape [n_samples, n_samples]
        The graph kernel built on the input data
        Only necessary for calculating Von Neumann Entropy

    diff_op : array-like, shape [n_samples, n_samples]
        The diffusion operator fit on the input data

    diff_potential : array-like, shape [n_samples, n_samples]
        Precomputed diffusion potential

    References
    ----------
    .. [1] `Moon KR, van Dijk D, Zheng W, et al. (2017). "PHATE: A
       Dimensionality Reduction Method for Visualizing Trajectory Structures in
       High-Dimensional Biological Data". Biorxiv.
       <http://biorxiv.org/content/early/2017/03/24/120378>`_
    """

    def __init__(self, n_components=2, a=10, k=5, t=30, mds='metric',
                 knn_dist='euclidean', mds_dist='euclidean', njobs=1,
                 random_state=None, verbose=True):
        self.ndim = n_components
        self.a = a
        self.k = k
        self.t = t
        self.mds = mds
        self.knn_dist = knn_dist
        self.mds_dist = mds_dist
        self.njobs = 1
        self.random_state = random_state
        self.verbose = verbose

        self.gs_ker = None
        self.diff_op = None
        self.diff_potential = None
        self.embedding = None
        self.X = None

    def reset_mds(self, n_components=None, mds=None, mds_dist=None):
        if n_components is not None:
            self.n_components = n_components
        if mds is not None:
            self.mds = mds
        if mds_dist is None:
            self.mds_dist = mds_dist
        self.embedding = None

    def reset_diffusion(self, t=None):
        if t is not None:
            self.t = t
        self.diff_potential = None

    def fit(self, X):
        """
        Computes the diffusion operator

        Parameters
        ----------
        X : array, shape=[n_samples, n_features]
            Input data.

        Returns
        -------
        phate : PHATE
        The estimator object
        """
        if self.X is not None and not np.all(X == self.X):
            """
            If the same data is used, we can reuse existing kernel and
            diffusion matrices. Otherwise we have to recompute.
            """
            self.gs_ker = None
            self.diff_op = None
            self.diff_potential = None
            self.embedding = None
        self.X = X
        if self.gs_ker is None or self.diff_op is None:
            self.diff_potential = None  # can't use precomputed potential
        self.gs_ker, self.diff_op = calculate_operator(
            X, a=self.a, k=self.k, knn_dist=self.knn_dist,
            njobs=self.njobs, gs_ker=self.gs_ker,
            diff_op=self.diff_op, verbose=self.verbose)
        return self

    def transform(self, X=None, t=None):
        """
        Computes the position of the cells in the embedding space

        Parameters
        ----------
        X : array, shape=[n_samples, n_features]
            Input data.

        t : int, optional, default: 30
            power to which the diffusion operator is powered
            sets the level of diffusion

        Returns
        -------
        embedding : array, shape=[n_samples, n_dimensions]
        The cells embedded in a lower dimensional space using PHATE
        """
        if self.X is not None and X is not None and not np.all(X == self.X):
            """
            sklearn.BaseEstimator assumes out-of-sample transformations are
            possible. We explicitly test for this in case the user is not aware
            that reusing the same diffusion operator with a different X will
            not give different results.
            """
            raise RuntimeWarning("Pre-fit PHATE cannot be used to transform a "
                                 "new data matrix. Please fit PHATE to the new"
                                 " data by running 'fit' with the new data.")
        if self.diff_op is None:
            raise NotFittedError("This PHATE instance is not fitted yet. Call "
                                 "'fit' with appropriate arguments before "
                                 "using this method.")
        if t is None:
            t = self.t
        else:
            self.t = t
        self.embedding, self.diff_potential = embed_mds(
            self.diff_op, t=t, n_components=self.ndim,
            diff_potential=self.diff_potential, embedding=self.embedding,
            mds=self.mds, mds_dist=self.mds_dist, njobs=self.njobs,
            random_state=self.random_state, verbose=self.verbose)
        return self.embedding

    def fit_transform(self, X, t=None):
        """
        Computes the diffusion operator and the position of the cells in the
        embedding space

        Parameters
        ----------
        X : array, shape=[n_samples, n_features]
            Input data.

        diff_op : array, shape=[n_samples, n_samples], optional
            Precomputed diffusion operator

        Returns
        -------
        embedding : array, shape=[n_samples, n_dimensions]
        The cells embedded in a lower dimensional space using PHATE
        """
        start = time.time()
        self.fit(X)
        self.transform(t=t)
        if self.verbose:
            print("Finished PHATE embedding in %.2f seconds.\n" %
                  (time.time() - start))
        return self.embedding

    def von_neumann_entropy(self, t_max=100):
        """
        Determines the Von Neumann entropy of the diffusion affinities
        at varying levels of t. The user should select a value of t
        around the "knee" of the entropy curve.

        We require that 'fit' stores the values of gs_ker and diff_deg
        in order to calculate the Von Neumann entropy. Alternatively,
        we could recalculate them here.

        Parameters
        ----------
        t_max : int
            Maximum value of t to test

        Returns
        -------
        entropy : array, shape=[t_max]
        The entropy of the diffusion affinities for each value of t
        """
        if self.gs_ker is None:
            raise NotFittedError("This PHATE instance is not fitted yet. Call "
                                 "'fit' with appropriate arguments before "
                                 "using this method.")
        diff_aff = np.diagflat(
            np.power(np.sum(self.gs_ker, axis=0), 1 / 2))
        diff_aff = np.matmul(np.matmul(diff_aff, self.gs_ker),
                             diff_aff)
        diff_aff = (diff_aff + diff_aff.T) / 2

        _, eigenvalues, _ = svd(diff_aff)
        entropy = []
        eigenvalues_t = np.copy(eigenvalues)
        for _ in range(t_max):
            prob = eigenvalues_t / np.sum(eigenvalues_t)
            prob = prob[prob > 0]
            entropy.append(-np.sum(prob * np.log(prob)))
            eigenvalues_t = eigenvalues_t * eigenvalues

        return np.array(entropy)
