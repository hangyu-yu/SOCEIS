# CNLS per-parameter curve-fit configuration

## Goal

Replace the current single, global curve-fit configuration with independent settings for every CNLS parameter, while retaining a fast batch-apply workflow.  A parameter must explicitly be selected before it is fitted, shown as a fitted trend, or reset from a fitted trend.

## Scope and non-goals

- This change applies only to the CNLS **CF option** window and the all-tab CNLS parameter plots.
- It leaves the existing file-level x-index workflow and the available fitting-model catalogue unchanged.
- It does not make settings persistent across application restarts.  They remain in the active project/session store, matching the existing CF option behaviour.

## Interaction design

### Batch controls

The top of the CF option window retains a single set of controls:

1. Category and fitting method.
2. Polynomial degree (visible/enabled only for Polynomial).
3. Confidence interval, displayed as a percentage and constrained to 50.00 through 99.99.
4. **Apply to selected**.

The Apply action copies the current method, degree and CI to every currently selected parameter.  Category is derived from the selected method and is not separately stored.

### Per-parameter cards

The lower portion of the window is a scrollable list of compact parameter cards.  Each card is a two-column, four-row layout:

| Left column | Right column |
| --- | --- |
| `checkbox + parameter name`, aligned top-left with the first row | 1. Category + Method |
| empty | 2. Degree (hidden or disabled for non-Polynomial methods) |
| empty | 3. CI (%) |
| empty | 4. Fit result: R² plus equation, or a readable fitting error |

Cards default to **unselected**.  Every card initially uses Polynomial, degree 1 and CI 95.00%, but its settings have no effect until the parameter is selected.  Editing a card immediately changes only that parameter, even after a batch apply.

### Actions

- **Fit data** fits exactly the selected parameters, each with its own method, degree and CI.  If no parameter is selected, show a warning and make no changes.
- **reset parameters** affects exactly the selected parameters that have a current successful fit.  It writes the prediction to the initial value and the per-parameter CI limits to its lower/upper bounds.
- An unselected parameter is not fitted, is not reset, and has no fitted line/band rendered in the all-tab plot.
- The existing x-index checkbox continues to gate the fitting controls.  Changing the selected parameter set or any per-parameter setting invalidates only the corresponding stale fit until it is run again.

## Data model and computation

Store configuration and fit results by the parameter's stable flat index rather than its display name, so repeated display names cannot overwrite one another.

Each configuration record contains:

```text
selected: bool
method: str
degree: int
confidence_level: float  # fractional value, e.g. 0.95
```

The curve-fitting engine will accept a confidence level per fit and persist it in the fit result.  `evaluate()` and `predict_at()` read that saved value when deriving the Student-t confidence band.  The module-level 95% constant is removed as the governing source of confidence, while a 0.95 default remains for backwards-compatible direct engine calls.

Plot lookup and reset lookup use the same index-keyed records.  This ensures a parameter's displayed curve, band and reset bounds always use the same method and CI that produced its fit.

## Error handling

- Retain existing model and point-count validation, but surface failures in the card's Fit result row.
- Reject out-of-range/non-finite CI values at both GUI and engine boundaries.
- Preserve existing handling for non-finite predictions and degenerate confidence intervals during reset.
- When the active circuit topology or parameter count changes, discard incompatible CF records and fits rather than applying them to different parameters.

## Verification

Add focused engine tests for confidence-level-sensitive intervals and backwards-compatible 95% defaults.  Add GUI-adjacent logic tests where practical for:

1. unselected parameters being omitted from fit/reset/plot lookup;
2. batch apply changing only selected parameter records;
3. individual overrides surviving a batch apply to other selected records; and
4. independent methods, degrees and CIs yielding independently stored results.

Manually exercise the CF option with multiple files and several parameters: apply a batch configuration to a subset, override one card, fit, inspect its plot and confidence band, then reset and verify only the selected parameters changed.
