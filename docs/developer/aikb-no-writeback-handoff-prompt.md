# AIKB No-Writeback Handoff Prompt

Use this prompt when asking AIKB to evaluate Netfix product optimization. Do not
write Netfix runtime truth into AIKB from this prompt.

```text
你是 AIKB 的 capability/router reviewer。本轮只做 no-writeback advisory review。

Owner repo:
/Users/qibaishi/Desktop/网络

Primary source:
docs/developer/capability-matrix.md
GET /dashboard/state contract: netfix_current_mac_state.v1

Review goals:
1. Evaluate whether Netfix product surfaces are now routed by current Mac state
   and one primary next action, instead of stacked features.
2. Review internal/external search and docs discoverability:
   README, README.en, AGENTS, developer docs, MCP tools, HTTP endpoints.
3. Review frontend/UI/UX:
   macOS Dashboard, Web dashboard, Settings proxy flow, AI explanation entry,
   recovery/blocking states, first-screen hierarchy.
4. Review product strength:
   ordinary-user proxy setup path, service mismatch handling, rollback trust,
   open-source positioning, contributor clarity.
5. Review open-source governance:
   capability matrix, confirmation boundaries, docs/API/MCP drift tests,
   release-readiness boundaries.
6. Review skill opportunities:
   identify whether an `open-source-governance-airlock` skill is still needed.
   Keep it candidate-only unless repeated use and non-overlap are proven.

Hard boundaries:
- Do not write back to AIKB as validated truth.
- Do not install plugins, create skills, or modify Netfix code.
- Treat screenshots, research reports, and this prompt as advisory evidence.
- Product/runtime truth remains in the Netfix owner repo.

Expected output:
- Findings grouped by product state contract, frontend hierarchy, docs/search,
  open-source governance, and skill candidates.
- Each finding cites exact owner-repo paths or endpoint contracts.
- Include no promotion, no validation, and no AIKB truth update claims.
```
