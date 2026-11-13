---
name: project-board
description: "Manage the The-Replacement roadmap project board: update issue status, track SDD phase progress, add issues to board."
compatibility: opencode
when_to_use: |
  - When an SDD phase completes and the board must be updated
  - When creating a new issue that should appear on the board
  - When needing to check or sync board state
allowed-tools:
  - Bash
  - mcp__n3rv-memory__memory_recall
  - mcp__n3rv-memory__memory_save
model: fast
effort: low
user-invocable: false
---

# Skill: project-board

## Board Identity

All commands target the **The-Replacement Roadmap** project board.

| Property | Value |
|----------|-------|
| Project number | `2` |
| Owner | `The-Replacement` |
| Project ID (GraphQL) | `PVT_kwDOE1iio84BrhYz` |

## Field IDs

### Status field

| Field ID | Type |
|----------|------|
| `PVTSSF_lADOE1iio84BrhYzzhpzwA4` | SingleSelect |

| Option | ID |
|--------|-----|
| Todo | `f75ad846` |
| In Progress | `47fc9ee4` |
| Done | `98236657` |

### SDD Phase field

| Field ID | Type |
|----------|------|
| `PVTSSF_lADOE1iio84BrhYzzhpzwK4` | SingleSelect |

| Option | ID | SDD Phase |
|--------|-----|-----------|
| Todo | `66fa4f7d` | No SDD work started |
| Explore | `751f2d04` | Phase 1 |
| Propose | `33e3a016` | Phase 2 |
| Spec | `ceb6e6d2` | Phase 3 |
| Design | `c0dcb7b5` | Phase 4 |
| Tasks | `d2705ad5` | Phase 5 |
| Apply | `704d0a09` | Phase 6 |
| Verify | `ca959d10` | Phase 7 |
| Done | `f94cb7b6` | Phase 8 (archived) |

## SDD Phase → Board Update Map

When an SDD phase completes, update the board as follows:

| SDD Phase Completes | Status | SDD Phase |
|---------------------|--------|-----------|
| explore | In Progress (`47fc9ee4`) | Explore (`751f2d04`) |
| propose | In Progress (`47fc9ee4`) | Propose (`33e3a016`) |
| spec | In Progress (`47fc9ee4`) | Spec (`ceb6e6d2`) |
| design | In Progress (`47fc9ee4`) | Design (`c0dcb7b5`) |
| tasks | In Progress (`47fc9ee4`) | Tasks (`d2705ad5`) |
| apply | In Progress (`47fc9ee4`) | Apply (`704d0a09`) |
| verify | In Progress (`47fc9ee4`) | Verify (`ca959d10`) |
| archive | Done (`98236657`) | Done (`f94cb7b6`) |

## Commands

### Update an item's Status

```bash
gh project item-edit \
  --id <ITEM_ID> \
  --field-id PVTSSF_lADOE1iio84BrhYzzhpzwA4 \
  --project-id PVT_kwDOE1iio84BrhYz \
  --single-select-option-id <OPTION_ID>
```

### Update an item's SDD Phase

```bash
gh project item-edit \
  --id <ITEM_ID> \
  --field-id PVTSSF_lADOE1iio84BrhYzzhpzwK4 \
  --project-id PVT_kwDOE1iio84BrhYz \
  --single-select-option-id <PHASE_OPTION_ID>
```

### Add an issue to the project board

```bash
gh project item-add 1 --owner The-Replacement --url <ISSUE_URL>
```

### Find an item ID from an issue number

```bash
gh api graphql -f query='query{organization(login:"The-Replacement"){projectV2(number:1){items(first:100){nodes{id content{...on Issue{number}}}}}}}' --jq '.data.organization.projectV2.items.nodes[] | select(.content.number == <ISSUE_NUMBER>) | .id'
```

Replace `<ISSUE_NUMBER>` with the actual issue number.

## Workflow: After SDD Phase Completion

After `memory_save` succeeds in any SDD phase skill, update the board:

1. Find the item ID for the issue
2. Update both Status and SDD Phase fields
3. Skip silently if the issue is not on the board

## Rules

- NEVER update the board before the memory_save succeeds. The board is downstream of MAGI.
- If `ITEM_ID` is empty (issue not on board), skip the update — do NOT fail the task.
- Always update both Status AND SDD Phase together for consistency.
- All commands use `--owner The-Replacement`, never `--org`.