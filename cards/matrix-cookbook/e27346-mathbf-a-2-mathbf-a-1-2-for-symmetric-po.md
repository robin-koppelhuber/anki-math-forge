---
uid: e27346
type: identity
status: approved
content_hash: a06403fff687c8dc
source: "Matrix Cookbook §3.1, eq. 154, p. 18"
unit: "matrix-cookbook:3.1:154"
frequency: core
derivation: short
tags: [condition-number, eigenvalues]
verify: false
---

## front
$\|\mathbf{A}\|_2\|\mathbf{A}^{-1}\|_2$ for symmetric positive definite $\mathbf{A}$

## back
$\frac{\max(\text{eig}(\mathbf{A}))}{\min(\text{eig}(\mathbf{A}))}$

## conditions
$\mathbf{A} \in \mathbb{R}^{n \times n}$; $\mathbf{A} = \mathbf{A}^T$; $\mathbf{x}^T\mathbf{A}\mathbf{x} > 0$ for every $\mathbf{x} \neq \mathbf{0}$, equivalently every eigenvalue is positive.

## uses
Convergence rates for gradient descent on a quadratic and for conjugate gradients.

## prose
For a symmetric positive definite matrix the singular values are the eigenvalues, so $\|\mathbf{A}\|_2 = \max(\text{eig}(\mathbf{A}))$ and the 2-norm condition number is the eigenvalue spread.

## notes
Symmetry and positive definiteness are printed in the sentence above eq. 154, not in the equation. Dropping them breaks the card: for a general $\mathbf{A}$, $\|\mathbf{A}\|_2 = \sqrt{\max(\text{eig}(\mathbf{A}^H\mathbf{A}))}$ and the eigenvalue ratio is wrong.
Eq. 154 as printed has an unbalanced parenthesis in its middle term, $\max(\text{eig}(\mathbf{A}))\max(\text{eig}(\mathbf{A}^{-1})))$. The same typo appears at eq. 545. The card carries only the final right-hand side, so it does not reach the deck.
