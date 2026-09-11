---
uid: c0bd89
type: identity
status: approved
content_hash: 8b5e19dd96f52997
source: "Matrix Cookbook §2.1, eq. 54, p. 9"
unit: "matrix-cookbook:2.1:53, matrix-cookbook:2.1:54"
frequency: rare
derivation: short
tags: [derivatives, determinant]
verify: true
---

## front
$\frac{\partial \det(\mathbf{X}^T\mathbf{A}\mathbf{X})}{\partial \mathbf{X}}$ for rectangular $\mathbf{X}\in\mathbb{R}^{m \times n}$

## back
$\det(\mathbf{X}^T\mathbf{A}\mathbf{X})\left(\mathbf{A}\mathbf{X}(\mathbf{X}^T\mathbf{A}\mathbf{X})^{-1} + \mathbf{A}^T\mathbf{X}(\mathbf{X}^T\mathbf{A}^T\mathbf{X})^{-1}\right)$

## conditions
$\mathbf{X} \in \mathbb{R}^{m \times n}$; $\mathbf{A} \in \mathbb{R}^{m \times m}$;
$\mathbf{X}^T\mathbf{A}\mathbf{X}$ and $\mathbf{X}^T\mathbf{A}^T\mathbf{X}$
invertible. Denominator layout.

## prose
The two terms coincide when $\mathbf{A} = \mathbf{A}^T$, collapsing to
$2\det(\mathbf{X}^T\mathbf{A}\mathbf{X})\mathbf{A}\mathbf{X}(\mathbf{X}^T\mathbf{A}\mathbf{X})^{-1}$.

## uses
Choosing where to measure so the estimate comes out most precise: maximise $\det(\mathbf{X}^T\mathbf{A}\mathbf{X})$ over the design $\mathbf{X}$ (D-optimal design).

## verify
```python
A = randn(5, 5)
X = randn(5, 3)
lhs = grad(lambda M: np.linalg.det(M.T @ A @ M), X)
S = X.T @ A @ X
rhs = np.linalg.det(S) * (
    A @ X @ np.linalg.inv(S) + A.T @ X @ np.linalg.inv(X.T @ A.T @ X)
)
```

## notes
The book prints the symmetric-$\mathbf{A}$ case separately as eq. 53; that
unit points at this card, and the collapse is in `## prose`.
symmetric"; invertibility of both quadratic forms added.
$\mathbf{A}$ need not be symmetric is now carried by the shapes
$m \times n$, $m \times m$ and by `## prose`.
$\partial\det(\mathbf{X}^T\mathbf{A}\mathbf{X})/\partial\mathbf{X}$, with the
English qualifier for square, invertible $\mathbf{X}$ on its front, and answers
$2\det(\mathbf{X}^T\mathbf{A}\mathbf{X})\mathbf{X}^{-T}$. The formula on this
card covers that case. Decide whether eq. 52 is worth a separate card.
