---
uid: 1adf44
type: identity
status: approved
content_hash: ce8c0035d5410d67
source: "Matrix Cookbook §2.6, eq. 129, p. 14"
unit: "matrix-cookbook:2.6:129"
gist: the gradient of a Euclidean distance
frequency: core
derivation: short
tags: [derivatives, norms, two-norm]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{x}}\|\mathbf{x}-\mathbf{a}\|_2$

## back
$\dfrac{\mathbf{x}-\mathbf{a}}{\|\mathbf{x}-\mathbf{a}\|_2}$

## conditions
$\mathbf{x} \neq \mathbf{a}$. Denominator layout.

## prose
The square root is what divides: its derivative $1/(2\sqrt{u})$ puts the norm in the denominator. It has to come out a unit vector, because walking straight away from $\mathbf{a}$ increases the distance at exactly unit rate.

## proof
$\|\mathbf{x}-\mathbf{a}\|_2 = \sqrt{u}$ with $u = (\mathbf{x}-\mathbf{a})^T(\mathbf{x}-\mathbf{a})$. Then $\partial u/\partial\mathbf{x} = 2(\mathbf{x}-\mathbf{a})$ and $d\sqrt{u}/du = 1/(2\sqrt{u})$, so the two factors of $2$ cancel and one factor of the norm is left downstairs.

## verify
```python
x = randn(5, 1)
a = randn(5, 1)
lhs = grad(lambda v: float(np.linalg.norm(v - a)), x)
rhs = (x - a) / np.linalg.norm(x - a)
```

## notes
