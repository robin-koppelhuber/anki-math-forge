---
uid: 2720f4
type: identity
status: approved
content_hash: ed7b2fcba5545bcc
source: "Matrix Cookbook §2.5, eq. 106, p. 13"
unit: "matrix-cookbook:2.5:106"
gist: the derivative of the trace of X squared
frequency: core
derivation: short
tags: [derivatives, trace]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{X}}\text{Tr}(\mathbf{X}^2)$

## back
$2\mathbf{X}^T$

## conditions
$\mathbf{X} \in \mathbb{R}^{n \times n}$. Denominator layout.

## prose
$\text{Tr}(\mathbf{X}^2) = \sum_{ij} X_{ij} X_{ji}$ pairs each entry with its mirror, which is where the transpose comes from; $\text{Tr}(\mathbf{X}^T\mathbf{X})$ pairs each entry with itself and gives $2\mathbf{X}$.

## proof
Entrywise, differentiating $\text{Tr}(\mathbf{X}^2) = \sum_{kl} X_{kl}X_{lk}$ in $X_{ij}$ picks out the two terms containing it, and $2X_{ji}$ is entry $(i,j)$ of $2\mathbf{X}^T$:
$$\frac{\partial}{\partial X_{ij}} \sum_{kl} X_{kl}X_{lk} = 2X_{ji}$$
Or by the product rule on the differential, reading the answer off $df = \text{Tr}(\mathbf{G}^T d\mathbf{X})$ with $\mathbf{G} = \partial f/\partial \mathbf{X}$, and using the cyclic property on the first trace:
$$\begin{aligned}
d\,\text{Tr}(\mathbf{X}^2) &= \text{Tr}\big((d\mathbf{X})\mathbf{X}\big) + \text{Tr}\big(\mathbf{X}(d\mathbf{X})\big) \\
&= 2\,\text{Tr}(\mathbf{X}\,d\mathbf{X})
\end{aligned}$$
so $\mathbf{G}^T = 2\mathbf{X}$, that is $\mathbf{G} = 2\mathbf{X}^T$.
