---
uid: 9a12f9
type: identity
status: approved
content_hash: bcd5ad344e05623a
source: "Matrix Cookbook §2.1, eq. 51, p. 9"
unit: "matrix-cookbook:2.1:51"
frequency: rare
derivation: short
tags: [derivatives, determinant]
verify: true
---

## front
$\frac{\partial \det(\mathbf{A}\mathbf{X}\mathbf{B})}{\partial \mathbf{X}}$

## back
$\det(\mathbf{A}\mathbf{X}\mathbf{B})(\mathbf{X}^{-1})^T$

## conditions
$\mathbf{X}, \mathbf{A}, \mathbf{B} \in \mathbb{R}^{n \times n}$, all
invertible. Denominator layout.

## prose
$\det(\mathbf{A}\mathbf{X}\mathbf{B}) = \det(\mathbf{A})\det(\mathbf{X})\det(\mathbf{B})$,
so $\mathbf{A}$ and $\mathbf{B}$ only scale the answer and it is
$\mathbf{X}^{-T}$ that appears, not $(\mathbf{A}\mathbf{X}\mathbf{B})^{-T}$.

## verify
```python
A = invertible(4)
B = invertible(4)
X = invertible(4)
lhs = grad(lambda M: np.linalg.det(A @ M @ B), X)
rhs = np.linalg.det(A @ X @ B) * np.linalg.inv(X).T
```

## notes
and $\mathbf{B}$ added. Without them
$\mathbf{B}(\mathbf{A}\mathbf{X}\mathbf{B})^{-1}\mathbf{A}$ does not collapse to
$\mathbf{X}^{-1}$.
$\det(\mathbf{A}\mathbf{X}\mathbf{B})(\mathbf{X}^T)^{-1}$; omitted from the back
as the same matrix.
