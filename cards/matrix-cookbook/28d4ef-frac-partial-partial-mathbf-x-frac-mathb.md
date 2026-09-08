---
uid: 28d4ef
type: identity
status: approved
content_hash: 2dcbc8038f8f2ca7
source: "Matrix Cookbook §2.4, eq. 94-95, p. 12"
unit: "matrix-cookbook:2.4:94, matrix-cookbook:2.4:95"
frequency: rare
derivation: short
tags: [derivatives, rayleigh-quotient]
verify: false
---

## front
$\frac{\partial}{\partial \mathbf{x}}\frac{(\mathbf{A}\mathbf{x})^T(\mathbf{A}\mathbf{x})}{(\mathbf{B}\mathbf{x})^T(\mathbf{B}\mathbf{x})}$

## back
$2\frac{\mathbf{A}^T\mathbf{A}\mathbf{x}}{\mathbf{x}^T\mathbf{B}^T\mathbf{B}\mathbf{x}} - 2\frac{\mathbf{x}^T\mathbf{A}^T\mathbf{A}\mathbf{x}\,\mathbf{B}^T\mathbf{B}\mathbf{x}}{(\mathbf{x}^T\mathbf{B}^T\mathbf{B}\mathbf{x})^2}$

## conditions
$\mathbf{B}\mathbf{x} \neq \mathbf{0}$. Denominator layout.

## prose
Setting it to zero gives
$\mathbf{A}^T\mathbf{A}\mathbf{x} = \lambda\,\mathbf{B}^T\mathbf{B}\mathbf{x}$
with $\lambda$ the quotient itself, so the stationary points of this
ratio of two quadratic forms (a generalised Rayleigh quotient) are the
vectors solving that eigenproblem (the generalised eigenvectors of
$(\mathbf{A}^T\mathbf{A}, \mathbf{B}^T\mathbf{B})$).

## notes
eq. 95 prints the first denominator as $\mathbf{x}^T\mathbf{B}\mathbf{B}\mathbf{x}$, with no transpose on either $\mathbf{B}$, while every other occurrence in eqs. 94-95 has $\mathbf{B}^T\mathbf{B}$. **The back is corrected, not as printed.**
Checked numerically against a central-difference gradient with a non-symmetric $\mathbf{B}$: the printed form is wrong by 8.6, the corrected form matches to 1.8e-08. A card is not a transcription: the crop is authoritative for what the book says, and this deck is what gets drilled, so a back known to be false does not stay. The book's form is recorded here and in sources/matrix-cookbook/README.md.
