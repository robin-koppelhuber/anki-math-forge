---
uid: 2d3bf4
type: identity
status: approved
content_hash: 0490c420b3974bd5
source: "Matrix Cookbook §1.3, p. 7"
unit: "matrix-cookbook:1.3:p7y427"
frequency: common
derivation: short
tags: [eigenvalues, two-by-two]
verify: true
---

## front
the eigenvalues of $\mathbf{A} \in \mathbb{R}^{2 \times 2}$

## back
$\lambda_{1,2} = \dfrac{\text{Tr}(\mathbf{A}) \pm \sqrt{\text{Tr}(\mathbf{A})^2 - 4\det(\mathbf{A})}}{2}$

## conditions
$\mathbf{A} \in \mathbb{R}^{2 \times 2}$; $\lambda_{1,2}$ taken over $\mathbb{C}$.

## proof
$\det(\mathbf{A} - \lambda\mathbf{I}) = \lambda^2 - \lambda\,\text{Tr}(\mathbf{A}) + \det(\mathbf{A})$; the quadratic formula on that polynomial gives the two roots.

## prose
The roots are real exactly when $\text{Tr}(\mathbf{A})^2 \ge 4\det(\mathbf{A})$, which a symmetric $\mathbf{A}$ always satisfies, its discriminant being $(A_{11}-A_{22})^2 + 4A_{12}^2$.

## verify
```python
P = invertible(2)
A = P @ np.diag(randn(2)) @ np.linalg.inv(P)
tr, det = np.trace(A), np.linalg.det(A)
root = np.sqrt(max(tr**2 - 4 * det, 0.0))
lhs = np.sort(np.array([(tr + root) / 2, (tr - root) / 2]))
rhs = np.sort(np.linalg.eigvals(A).real)
```
