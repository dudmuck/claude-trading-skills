---
layout: default
title: "Econ Indicator Explainer"
grand_parent: English
parent: Skill Guides
nav_order: 25
lang_peer: /ja/skills/econ-indicator-explainer/
permalink: /en/skills/econ-indicator-explainer/
generated: true
---

# Econ Indicator Explainer
{: .no_toc }

Static knowledge base for ~30 economic indicators. Given an indicator name (or FMP event name like 'Consumer Price Index (CPI) YoY'), returns a structured 'why it matters' card with: what it is, how it's measured, why it matters for markets, typical 60-min reaction history (SPY/TLT/DXY/VIX), and what to watch for in today's print. Used by morning-trading-briefing skill to enrich raw economic-calendar-fetcher output. No API calls — fast, deterministic, version-controlled.
{: .fs-6 .fw-300 }

<span class="badge badge-free">No API</span>

[View Source on GitHub](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/econ-indicator-explainer){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>Table of Contents</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. Overview

# Econ Indicator Explainer

---

## 2. Prerequisites

- Static lookup against a version-controlled reference file; no API calls, works offline
- Python 3.9+ recommended

---

## 3. Quick Start

Invoke this skill by describing your analysis needs to Claude.

---

## 4. Workflow

See the skill's SKILL.md for the complete workflow.

---

## 5. Resources

**References:**

- `skills/econ-indicator-explainer/references/indicators.md`

**Scripts:**

- `skills/econ-indicator-explainer/scripts/lookup_indicator.py`
