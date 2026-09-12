---
uid: 13115c
type: identity
status: approved
content_hash: 2b42762a4120e45b
source: "Matrix Cookbook §2.4, eq. 70, p. 10"
unit: "matrix-cookbook:2.4:70"
gist: the derivative of a bilinear form in a matrix
frequency: core
derivation: short
tags: [derivatives, linear-forms]
verify: true
---

## front
$\frac{\partial \mathbf{a}^T\mathbf{X}\mathbf{b}}{\partial \mathbf{X}}$

## back
$\mathbf{a}\mathbf{b}^T$

## conditions
Denominator layout.

## proof
$d(\mathbf{a}^T\mathbf{X}\mathbf{b}) = \text{Tr}(\mathbf{b}\mathbf{a}^T\,d\mathbf{X})$;
reading a differential as $\text{Tr}(\mathbf{G}^T\,d\mathbf{X})$ gives
$\mathbf{G} = \mathbf{a}\mathbf{b}^T$.

## verify
```python
X = randn(4, 3)
a = randn(4, 1)
b = randn(3, 1)
lhs = grad(lambda M: (a.T @ M @ b)[0, 0], X)
rhs = a @ b.T
```

## notes
cookbook lays this out with the shape of X — with X 4×3, ab^T is 4×3 — and so
does `verify.grad`, whose docstring says "Denominator layout: the result has
the shape of `x`, matching the cards". Every §2.4 card follows the source. The
CLAUDE.md sentence looks like the thing to fix.
