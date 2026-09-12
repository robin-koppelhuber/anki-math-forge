---
uid: "1039e9"
type: identity
status: approved
content_hash: af23978e45a7383c
source: "Matrix Cookbook §1.3, p. 7"
unit: "matrix-cookbook:1.3:p7y407"
gist: the characteristic equation of a 2 by 2 matrix
frequency: common
derivation: short
tags: [eigenvalues, characteristic-polynomial, two-by-two]
verify: true
---

## front
the characteristic equation of $\mathbf{A} \in \mathbb{R}^{2 \times 2}$

## back
$\lambda^2 - \lambda\,\text{Tr}(\mathbf{A}) + \det(\mathbf{A}) = 0$

## prose
Reading the coefficients as the sum and the product of the roots gives $\lambda_1 + \lambda_2 = \text{Tr}(\mathbf{A})$ and $\lambda_1\lambda_2 = \det(\mathbf{A})$ (Vieta's formulas).

## proof
$\det(\mathbf{A} - \lambda\mathbf{I}) = (A_{11}-\lambda)(A_{22}-\lambda) - A_{12}A_{21} = \lambda^2 - \lambda(A_{11}+A_{22}) + (A_{11}A_{22}-A_{12}A_{21})$, whose two coefficients are $\text{Tr}(\mathbf{A})$ and $\det(\mathbf{A})$.

## verify
```python
P = invertible(2)
A = P @ np.diag(randn(2)) @ np.linalg.inv(P)
lam = np.linalg.eigvals(A).real
lhs = lam**2 - lam * np.trace(A) + np.linalg.det(A)
rhs = np.zeros(2)
```
