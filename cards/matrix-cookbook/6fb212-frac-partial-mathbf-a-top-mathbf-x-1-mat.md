---
uid: 6fb212
type: identity
status: approved
content_hash: ba04b58072dc4382
source: "Matrix Cookbook §2.2, eq. 61, p. 10"
unit: "matrix-cookbook:2.2:61"
frequency: common
derivation: short
tags: [derivatives, inverse]
verify: true
---

## front
$\frac{\partial\, \mathbf{a}^\top\mathbf{X}^{-1}\mathbf{b}}{\partial \mathbf{X}}$

## back
$-\mathbf{X}^{-\top}\mathbf{a}\mathbf{b}^\top\mathbf{X}^{-\top}$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$ invertible;
$\mathbf{a}, \mathbf{b} \in \mathbb{R}^{n}$. Denominator layout.

## prose
The order reverses under the transpose: $\mathbf{b}$ sits to the right of $\mathbf{a}$ on the right-hand side even though it sits to the right of $\mathbf{X}^{-1}$ on the left.

## proof
$d(\mathbf{a}^\top\mathbf{X}^{-1}\mathbf{b}) = -\mathbf{a}^\top\mathbf{X}^{-1}(d\mathbf{X})\mathbf{X}^{-1}\mathbf{b} = -\operatorname{Tr}(\mathbf{X}^{-1}\mathbf{b}\mathbf{a}^\top\mathbf{X}^{-1}\, d\mathbf{X})$;
reading that as $\operatorname{Tr}(\mathbf{G}^\top d\mathbf{X})$ gives $\mathbf{G} = -(\mathbf{X}^{-1}\mathbf{b}\mathbf{a}^\top\mathbf{X}^{-1})^\top$.

## verify
```python
X = invertible(4)
a = randn(4)
b = randn(4)
Xi = np.linalg.inv(X)
lhs = grad(lambda M: a @ np.linalg.inv(M) @ b, X)
rhs = -Xi.T @ np.outer(a, b) @ Xi.T
```
