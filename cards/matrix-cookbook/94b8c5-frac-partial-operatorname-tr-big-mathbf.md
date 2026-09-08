---
uid: 94b8c5
type: identity
status: approved
content_hash: 4cf3a4d50ef85001
source: "Matrix Cookbook §2.2, eq. 64, p. 10"
unit: "matrix-cookbook:2.2:64"
frequency: rare
derivation: short
tags: [derivatives, inverse, trace]
verify: true
---

## front
$\frac{\partial \operatorname{Tr}\big((\mathbf{X}+\mathbf{A})^{-1}\big)}{\partial \mathbf{X}}$

## back
$-\big((\mathbf{X}+\mathbf{A})^{-2}\big)^{\top}$

## conditions
$\mathbf{X}, \mathbf{A} \in \mathbb{R}^{n \times n}$; $\mathbf{X} + \mathbf{A}$
invertible. Denominator layout.

## proof
$d(\mathbf{X}+\mathbf{A})^{-1} = -(\mathbf{X}+\mathbf{A})^{-1}(d\mathbf{X})(\mathbf{X}+\mathbf{A})^{-1}$ since $d(\mathbf{X}+\mathbf{A}) = d\mathbf{X}$,
and cyclicity of the trace collects the two factors into $(\mathbf{X}+\mathbf{A})^{-2}$.

## prose
The shift $\mathbf{A}$ never leaves the inverse, because differentiating $\mathbf{X}+\mathbf{A}$ in $\mathbf{X}$ returns $d\mathbf{X}$ unchanged.

## verify
```python
A = randn(4, 4)
X = invertible(4)
Y = np.linalg.inv(X + A)
lhs = grad(lambda M: np.trace(np.linalg.inv(M + A)), X)
rhs = -(Y @ Y).T
```

## notes
This is $\mathbf{A}=\mathbf{B}=\mathbf{I}$ in eq. 63 with $\mathbf{X}$ shifted. Kept because recognising that substitution is the work; reject if the deck would rather carry only eq. 63.
