---
uid: 304b56
type: identity
status: approved
content_hash: f640c31cd4e67f8f
source: "Matrix Cookbook §2.3, eq. 68, p. 10"
unit: "matrix-cookbook:2.3:68"
gist: how an eigenvector moves when the matrix does
frequency: rare
derivation: short
tags: [derivatives, eigenvalues, perturbation]
verify: true
---

## front
$\partial \mathbf{v}_i$ in terms of $\partial \mathbf{A}$

## back
$(\lambda_i\mathbf{I}-\mathbf{A})^{+}(\partial \mathbf{A})\, \mathbf{v}_i$

## conditions
$\mathbf{A} \in \mathbb{R}^{n \times n}$, $\mathbf{A} = \mathbf{A}^\top$;
$\lambda_i$ a simple eigenvalue of $\mathbf{A}$ with eigenvector
$\mathbf{v}_i$, $\mathbf{v}_i^\top\mathbf{v}_i = 1$.

## prose
$(\cdot)^{+}$ inverts what is invertible and zeroes the rest (the Moore-Penrose pseudo-inverse);
$\lambda_i\mathbf{I}-\mathbf{A}$ is singular exactly along $\mathbf{v}_i$, and
that is the direction $\mathbf{v}_i^\top\mathbf{v}_i = 1$ has already pinned
down, so the pseudo-inverse returns the one perturbation orthogonal to
$\mathbf{v}_i$.

## uses
Backpropagation through a symmetric eigendecomposition; the sensitivity of PCA directions to a perturbed covariance.

## proof
Differentiating $\mathbf{A}\mathbf{v}_i = \lambda_i\mathbf{v}_i$ gives
$(\lambda_i\mathbf{I}-\mathbf{A})\,\partial\mathbf{v}_i = (\partial\mathbf{A})\mathbf{v}_i - (\partial\lambda_i)\mathbf{v}_i$.
Applying $(\lambda_i\mathbf{I}-\mathbf{A})^{+}$ drops the $(\partial\lambda_i)\mathbf{v}_i$ term, since $(\lambda_i\mathbf{I}-\mathbf{A})^{+}\mathbf{v}_i = \mathbf{0}$.

## verify
```python
Q = orth(4)
A = Q @ np.diag([1.0, 2.0, 3.0, 4.0]) @ Q.T
v = Q[:, 2]
u = randn(4)
def proj(M):
    w, V = np.linalg.eig(M)
    z = V[:, np.argsort(w.real)[2]].real
    return float(u @ (z * np.sign(z @ v)))
lhs = grad(proj, A)
rhs = np.linalg.pinv(3.0 * np.eye(4) - A) @ np.outer(u, v)
```

## notes
Moore-Penrose pseudo-inverse. It defines notation rather than bounding the
identity, and the deck declares no ambient meaning for $^{+}$.
