# Product Specification

## User promise

Given a proposed Irish development, estimate submission-time planning risk, identify recurring issues, show comparable decisions and let the user test realistic design changes.

## V1 output

Show a calibrated risk estimate or risk band, model version, council confidence metadata, top comparable applications, outcome mix, recurring refusal/FI themes from evidence, and an explicit sensitivity-analysis disclaimer.

## Scenario requirements

The first scenario release must support:

- baseline plus multiple named scenarios;
- units, storeys, height, site area, parking and description changes where the model contract supports them;
- side-by-side baseline/scenario scores;
- field-level change list;
- comparable-case outcome context for each scenario;
- no claim that a score delta is a causal guarantee;
- preservation of model version and input data for reproducibility.

Suggested first mutations are reducing units, reducing storeys, removing a basement/demolition term from the description only when the user confirms the physical change, and adding structured mitigation fields once they exist. Text-only edits must be labelled as language sensitivity, not design advice.

## Later stages

1. Model explanation.
2. Scenario simulation.
3. Matched precedent support.
4. Refused -> revised -> granted revision-pair support.
5. Evidence-backed recommendations with realistic bounds.

Automatic optimisation and development-value objectives are later capabilities, not part of the first scenario release.
