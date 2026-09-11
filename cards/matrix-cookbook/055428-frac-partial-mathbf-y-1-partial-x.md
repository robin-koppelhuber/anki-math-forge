---
uid: "055428"
type: identity
status: approved
content_hash: 920fe4a16eb75c68
source: "Matrix Cookbook §2.2, eq. 59, p. 9"
unit: "matrix-cookbook:2.2:59"
frequency: core
derivation: short
tags: [derivatives, inverse]
verify: true
---

## front
$\frac{\partial \mathbf{Y}^{-1}}{\partial x}$

## back
$-\mathbf{Y}^{-1}\frac{\partial \mathbf{Y}}{\partial x}\mathbf{Y}^{-1}$

## conditions
$\mathbf{Y}(x) \in \mathbb{R}^{n \times n}$ invertible; $x \in \mathbb{R}$.

## prose
The matrix analogue of $(1/y)' = -y'/y^2$, with the two factors of $\mathbf{Y}^{-1}$ kept on opposite sides of $\partial\mathbf{Y}/\partial x$ because matrices do not commute.

## proof
Differentiate $\mathbf{Y}\mathbf{Y}^{-1} = \mathbf{I}$:
$\frac{\partial \mathbf{Y}}{\partial x}\mathbf{Y}^{-1} + \mathbf{Y}\frac{\partial \mathbf{Y}^{-1}}{\partial x} = \mathbf{0}$,
then left-multiply by $\mathbf{Y}^{-1}$.

## verify
```python
# A scalar parameter, so the difference is taken in x rather than
# entrywise in a matrix: `grad` walks the entries of its argument.
A = randn(4, 4)
B = randn(4, 4)
Y = lambda t: A + t * B          # noqa: E731 - dY/dx is exactly B
h = 1e-6
lhs = (np.linalg.inv(Y(h)) - np.linalg.inv(Y(-h))) / (2 * h)
Yi = np.linalg.inv(Y(0.0))
rhs = -Yi @ B @ Yi
```

## notes
front already writes the derivative, so it only says the expression is
well-formed.
