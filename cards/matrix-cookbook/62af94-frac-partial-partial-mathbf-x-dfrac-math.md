---
uid: 62af94
type: identity
status: approved
content_hash: 1a590cc84404380e
source: "Matrix Cookbook §2.6, eq. 130, p. 14"
unit: "matrix-cookbook:2.6:130"
gist: the derivative of a normalised difference
frequency: rare
derivation: short
tags: [derivatives, norms, two-norm]
verify: true
---

## front
$\frac{\partial}{\partial \mathbf{x}}\dfrac{\mathbf{x}-\mathbf{a}}{\|\mathbf{x}-\mathbf{a}\|_2}$

## back
$\dfrac{\mathbf{I}}{\|\mathbf{x}-\mathbf{a}\|_2}-\dfrac{(\mathbf{x}-\mathbf{a})(\mathbf{x}-\mathbf{a})^\top}{\|\mathbf{x}-\mathbf{a}\|_2^3}$

## conditions
$\mathbf{x} \neq \mathbf{a}$.

## prose
Writing $r = \|\mathbf{x}-\mathbf{a}\|_2$ and $\hat{\mathbf{u}} = (\mathbf{x}-\mathbf{a})/r$, this is $(\mathbf{I}-\hat{\mathbf{u}}\hat{\mathbf{u}}^\top)/r$, the projection onto the directions orthogonal to $\hat{\mathbf{u}}$ scaled by $1/r$, because sliding along $\hat{\mathbf{u}}$ does not turn it.

## uses
Backpropagation through $L_2$ normalisation; how a bearing to a target swings as the sensor moves.

## verify
```python
a = randn(5)
x = a + randn(5)
u = randn(5)
r = np.linalg.norm(x - a)
lhs = grad(lambda z: u @ (z - a) / np.linalg.norm(z - a), x)
rhs = (np.eye(5) / r - np.outer(x - a, x - a) / r**3) @ u
```
