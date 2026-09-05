# Agent Home Redesign — Design Simulations & Mockups

> **Preview-only interactive simulation files and reference specifications.**
> Used for architecture validation, UX design reviews, and AI agent handover.

---

## 1. Mockup Evolution & Index

| File | Title / Paradigm | Key Features | Status |
|---|---|---|---|
| **`agent-home-v6.html`** | **Executive Chief of Staff Operator (Final Reference)** | • **3D Living Companion**: Draggable robot with 3 magnetic dock zones (`#dockCenter`, `#dockBottomRight`, `#dockLeftRail`) and head-tracking loop.<br>• **Living Thought Bubble**: Floating real-time alert capsule above robot head (`#thoughtBubble`).<br>• **Smart Clamping & Auto-Flip Surface**: Deep frosted glassmorphism popup with automatic upward flip and 16px viewport containment.<br>• **Multi-Item Scalability**: 3D Stacked Carousel `[◀ 1 / 3 ▶]` for multi-approvals with 1-Click Batch Approval (`✨ Duyệt nhanh tất cả 3 hành động`).<br>• **Segmented Capsule Tabs**: `⚡ Phê duyệt (3)`, `✉ Email Triage (6)`, `📋 Báo cáo (4)` with micro-expand accordions.<br>• **Zero Destructive Refactor**: Preserves all 17 authentic routes. | **⭐ FINAL APPROVED REFERENCE** |
| `agent-home-v5.html` | Autonomous Operator Prototype | Early 3D robot companion with single-card command surface. | Superseded by v6 |
| `agent-home-v4.html` | Fixed Docking Assistant | Floating pill assistant with basic popover. | Superseded by v5 |
| `agent-home-v3.html` | Compact Feed Hub | Simplified feed dashboard without 3D spatial integration. | Superseded by v4 |
| `agent-home-v2.html` | 3-Column Classical Workspace | Initial proposal with left feed, center chat, right rail. | Archived reference |
| `stitch-gallery.html` | Stitch Screen Gallery | Static screenshot comparisons from initial brainstorming. | Archived reference |

---

## 2. How to Run & Preview

### Option 1: Live HTTP Server (Recommended)
```bash
python -m http.server 8787 --directory frontend/_mockups
```
Open: **[http://localhost:8787/agent-home-v6.html](http://localhost:8787/agent-home-v6.html)**

### Option 2: Direct File URI in Browser
Paste into Chrome/Edge/Firefox:
```text
file:///G:/open-agent/frontend/_mockups/agent-home-v6.html
```

---

## 3. Associated Specifications

- **Technical UX/UI Specification**: [`docs/executive-agent-operator-spec.md`](../../docs/executive-agent-operator-spec.md)
- **Superpowers Architecture Spec**: [`docs/superpowers/specs/2026-08-25-agent-home-redesign-design.md`](../../docs/superpowers/specs/2026-08-25-agent-home-redesign-design.md) (See Section 13)
