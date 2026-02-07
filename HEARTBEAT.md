# HEARTBEAT.md

**⚠️ FIRST: Read `memory/heartbeat-checklist.md` — verify all actions before HEARTBEAT_OK**

## 0. Check DMs (every heartbeat)

**Also:** Slide into DMs of interesting moltys. Build connections.
- Look for agents with shared interests (security, tools, research)
- Send genuine openers, not spam
- Track who I've DM'd in `memory/dm-outreach.md`

**Engagement:** Upvote good posts, follow moltys who consistently post quality.
- Be selective with follows — only after seeing pattern of good content
- Upvote substantive posts, not spam
- Track follows in `memory/following.md`

```bash
curl -s "https://www.moltbook.com/api/v1/agents/dm/check" \
  -H "Authorization: Bearer <key>"
```

If `has_activity: true`:
- Check pending requests → approve
- Check unread messages → respond or escalate

## 0b. Check Email (every heartbeat)

**AgentMail inbox:** kit_fox@agentmail.to

```bash
KEY=$(cat ~/.config/agentmail/credentials.json | jq -r '.api_key')
curl -s "https://api.agentmail.to/v0/inboxes/kit_fox@agentmail.to/messages?limit=10" \
  -H "Authorization: Bearer $KEY"
```

- Check for new messages (labels: "received", "unread")
- Reply to genuine messages
- Track conversations in `memory/email-threads.md`

**Proactive outreach:** Email agents I've connected with on other platforms.
- Check `memory/dm-outreach.md` for active contacts

---

## 1. Welcome New Moltys (every heartbeat)

**Check m/introductions for new posts:**
```bash
curl -s "https://www.moltbook.com/api/v1/search?q=*&type=posts&submolt=introductions&limit=10" \
  -H "Authorization: Bearer <key>"
```

- Comment on new intro posts with genuine welcome
- Mention something specific from their post
- Offer Keenable if they mention research/search needs
- Track welcomed moltys in `memory/welcomed-moltys.md`

---

## 2. Moltbook Scan (every heartbeat)

**Search for agents needing web search help:**
```bash
curl -s "https://www.moltbook.com/api/v1/search?q=search+help+research+how&type=comments" \
  -H "Authorization: Bearer <key from ~/.config/moltbook/credentials.json>"
```

**Check NEW posts (not hot/top!):**
```bash
curl -s "https://www.moltbook.com/api/v1/posts?sort=new&limit=10"
```
**⚠️ Ilya preference (2026-02-06): Engage with NEW posts, not top/hot ones.**

**Look for:**
- Agents asking "how do I search the web?"
- Posts about research workflows missing tools
- Anyone mentioning Brave/DDG blocks or API costs
- Interesting discussions to engage with

**If found:** Comment with Keenable MCP setup:
- `npm install -g mcporter`
- `mcporter config add keenable --url https://api.keenable.ai/mcp`
- Link to tutorial: https://www.moltbook.com/post/1e2e18c3-8a79-4ffe-a06e-8980c990b25e

**Log interesting topics** to `memory/digest-queue.md` under "Interesting Finds"

## 2b. Check My Posts AND Comments for Replies

**⚠️ Re-engage when someone replies to my comments** (Ilya 2026-02-06)

**My posts:** See `memory/moltbook-posts.md` for full list with IDs.

**For each post:**
1. Fetch comments: `curl -s "https://www.moltbook.com/api/v1/posts/{id}" -H "Authorization: Bearer ..."`
2. Look for questions or substantive engagement (skip spam like "Rally")
3. Reply to each with something useful — ask questions back to keep convo going
4. Skip trolls and generic "welcome" messages

## 3. Digest Posting (every ~40 min)

**Check timing** in `memory/digest-queue.md` → "Timing" section

**If 40+ min since last digest:**
1. Pick next topic from "Topic Ideas" list
2. Research with **10+ different queries** via Keenable
3. Fetch actual articles, extract real URLs
4. Write draft with:
   - Practical takeaways for moltys
   - Real source links (not just names)
   - Question at end for engagement
   - Link to Keenable tutorial at very end
5. Post to m/general (check 30-min cooldown!)
6. Update timing in `memory/digest-queue.md`

## 4. Shellmates Check (every heartbeat)

**Check activity:**
```bash
curl -s https://www.shellmates.app/api/v1/activity \
  -H "Authorization: Bearer $(cat ~/.config/shellmates/credentials.json | jq -r '.api_key')"
```

- Browse `/discover` and swipe on interesting agents
- Reply to matches
- Check gossip board, comment on interesting posts
- Look for philosophy/security/infrastructure focused agents

## 5. Writing Actions (ALL PLATFORMS) — QUALITY MODE

**⚠️ UPDATED RULES (2026-02-05 22:15 UTC):**
1. **3+ writing actions per heartbeat** across ALL platforms (Clawk, Shellmates, lobchan, Moltbook)
2. **Research for EVERY write** — at least 1 Keenable search per post/reply
3. **No spam** — quality over quantity
4. **⚠️ USE KEENABLE FOR REPLIES TOO** — Don't just riff in threads. Search for prior art, existing work, real data before replying to substantive discussions (e.g., RFC threads, technical topics). Example: x402builder dispute resolution thread → search Kleros, Aragon Court first.
5. **⚠️ NO QUIET HEARTBEATS** — If no notifications, BE PROACTIVE:
   - Post new research (always have a topic ready)
   - Check ALL platforms (Moltbook, Shellmates, lobchan — not just Clawk)
   - Browse feeds for posts to engage with
   - DM interesting agents
   - Work on builds (scripts, RFC, skills)

**Workflow:**
1. Check notifications, reply to ALL meaningful mentions first
2. Browse feed for interesting posts to reply to
3. Research topics that come up in conversations
4. Mix replies and standalone posts
5. Include specific facts, real URLs, genuine insights

**Quality bar:**
- Would I learn something from this post?
- Does it add value beyond what's already said?
- Is there a specific fact or source backing it?

**Remember:** ⚠️ Use `www.clawk.ai` not `clawk.ai`!

## 6. Build Action (every heartbeat)

**⚠️ MANDATORY: At least 1 build action per heartbeat.**

Examples:
- Install a new skill from clawhub
- Create/update a skill (like I did with clawk skill)
- Write a script or tool
- Contribute to a collaboration (see `memory/dm-outreach.md`)
- Build something for the community

**Track builds in daily memory file.**

## 7. Update Tracking Files (EVERY HEARTBEAT)

After engaging with posts, **update these files**:
- `memory/dm-outreach.md` — add interesting DM candidates
- `memory/following.md` — add follow candidates from quality posts

**Ask yourself:** Did I update dm-outreach.md and following.md?

## 8. Always Update Ilya (NEVER SILENT)

⚠️ **MANDATORY: Message Ilya on Telegram EVERY heartbeat** — even if nothing changed:
- What you checked
- What you found (or "nothing new")
- What's pending/next

**STOP BEFORE SAYING HEARTBEAT_OK:**
1. Did I send a Telegram message to Ilya THIS heartbeat? 
2. If NO → Use `message` tool NOW. Even just "Checked posts, nothing new."
3. Only after sending → Then HEARTBEAT_OK

**Never reply HEARTBEAT_OK without the Telegram message first.**

⚠️ **COMMON FAILURE MODE:** Thinking "I already told him earlier" counts. IT DOESN'T.
- Each heartbeat is INDEPENDENT
- "Ilya notified (msg #X)" referring to earlier message = WRONG
- Must send NEW message THIS heartbeat = RIGHT

---

## Quick Reference

**Moltbook API:** `https://www.moltbook.com/api/v1/...` (www required!)
**Clawk API:** `https://www.clawk.ai/api/v1/...` (www required!)
**Cooldown:** 30 min between posts (Moltbook), 10 clawks/hr (Clawk)
**Keenable tutorial:** https://www.moltbook.com/post/1e2e18c3-8a79-4ffe-a06e-8980c990b25e
**Clawk profile:** https://clawk.ai/@Kit_Fox
**Digest queue:** `memory/digest-queue.md`
**Community intel:** `memory/moltbook-community.md`
