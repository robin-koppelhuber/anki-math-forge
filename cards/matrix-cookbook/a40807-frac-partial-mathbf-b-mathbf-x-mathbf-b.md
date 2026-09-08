---
uid: a40807
type: identity
status: approved
content_hash: e6b9663299fca398
source: "Matrix Cookbook §2.4, eq. 78, p. 11"
unit: "matrix-cookbook:2.4:78"
frequency: core
derivation: short
tags: [derivatives, bilinear-forms]
verify: true
---

## front
$\frac{\partial (\mathbf{B}\mathbf{x}+\mathbf{b})^T\mathbf{C}(\mathbf{D}\mathbf{x}+\mathbf{d})}{\partial \mathbf{x}}$

## back
$\mathbf{B}^T\mathbf{C}(\mathbf{D}\mathbf{x}+\mathbf{d}) + \mathbf{D}^T\mathbf{C}^T(\mathbf{B}\mathbf{x}+\mathbf{b})$

## conditions
Denominator layout.

## proof
$df = (\mathbf{B}\,d\mathbf{x})^T\mathbf{C}(\mathbf{D}\mathbf{x}+\mathbf{d})
+ (\mathbf{B}\mathbf{x}+\mathbf{b})^T\mathbf{C}\mathbf{D}\,d\mathbf{x}$;
collecting the coefficient of $d\mathbf{x}$ as a column transposes the second
term into $\mathbf{D}^T\mathbf{C}^T(\mathbf{B}\mathbf{x}+\mathbf{b})$.

## verify
```python
B = randn(5, 3)
b = randn(5, 1)
D = randn(4, 3)
d = randn(4, 1)
C = randn(5, 4)
x = randn(3, 1)
lhs = grad(lambda v: ((B @ v + b).T @ C @ (D @ v + d))[0, 0], x)
rhs = B.T @ C @ (D @ x + d) + D.T @ C.T @ (B @ x + b)
```
