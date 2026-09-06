# Privacy Policy — sdvx-b50-discord-bot

_Effective date: September 5, 2026_

This Privacy Policy explains what information **sdvx-b50-discord-bot** ("the Bot") collects, stores, and uses. By using the Bot, you agree to this policy.

## What the Bot does

The Bot is a Discord application that generates a Sound Voltex **B50** card image (top-50 Volforce) for a given Tachi/Kamaitachi username, using `/b50`, and lets users remember their own username with `/link` (removed with `/unlink`).

## Information we collect

**Provided by you (command arguments):**

- A **Tachi username** you pass to `/b50` (this may be your own or another player's public username) or to `/link`.

**Stored locally by the Bot (on the machine/server running it):**

- **`links.db`** — the mapping between your **Discord user ID** and your Tachi username, created when you run `/link`.
- **`stats.db`** — **query statistics**: command type (`/b50`, `/link`, `/unlink`), the `/b50` mode (`nabla` or `exceed`), your Discord user ID, the target Tachi username, and a timestamp, for each command invocation.
- **Jacket cache** — downloaded song cover images (public artwork) used to render the card, keyed by song ID.

**Fetched from public sources (not stored by us beyond the above):**

- **Public Tachi/Kamaitachi data** (`kamai.tachi.ac`) — the public profile and SDVX personal-best scores for the username supplied. The Bot does **not** log in to Tachi or access private data.
- **Song cover art** (`sdvx.dev`) — used only to render the image.

## What we do NOT collect

- **Message content** — the Bot is slash-command-only and never reads or stores messages.
- **Email, phone, real name** or any other account details.
- **Cookies, tracking, or analytics services** — none are used (statistics are counted by the Bot's own local counters only).

## How we use your information

- To answer `/b50` requests and render the requested image.
- To remember your `/link` so `/b50` works without an argument.
- To count usage (number and type of queries) via `stats.db`.

## Sharing

The Bot does **not** sell, rent, or share your information with third parties. Data is disclosed only if required by law or in response to a lawful request. The Bot's own storage (links and statistics) remains on the host running it and is not transmitted anywhere except that fetch requests are made to Tachi and the cover-art service to fulfil commands.

## Data retention & deletion

- Your `/link` mapping is deleted immediately when you run `/unlink`.
- Statistics rows may be retained as usage counts; they contain your Discord user ID and the usernames involved. You can ask for them to be removed by opening an issue in this repository.
- Data held by third parties (Tachi, Discord, the cover-art service) is governed by their own policies; the Bot does not control or retain it beyond the uses described above.

## Data security

The Bot stores data in local SQLite files on the host and takes reasonable care to prevent unauthorized access. No security measure is perfect, and we cannot guarantee absolute security. The Bot itself contains no secrets; the bot token is held privately by the operator and is never included in this repository.

## Changes to this policy

We may update this policy from time to time; the current version always lives in this repository. Continued use of the Bot after changes indicates acceptance.

## Contact

Questions or deletion requests: open an issue at **https://github.com/John-UNOwen/SDVX-B50-Image-Bot/issues**.
