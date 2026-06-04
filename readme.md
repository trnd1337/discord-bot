# Discord Moderation & Utility Bot / Bot de moderare și utilități Discord

A polished `discord.py` bot featuring advanced moderation, gaming utilities (League of Legends tracker), network utilities (IP lookup and ping), fun commands, and hybrid support for both slash commands and mention-based text commands.

Un bot `discord.py` complet pentru moderare și utilități, echipat cu comenzi slash, comenzi prin mențiune, embed-uri atractive, verificări mai sigure de rol, căutare IP public via ipinfo.io, tracker League of Legends și instrumente de rețea.

---

## Features / Funcționalități

### General & Fun / Generale și Divertisment

- `/help` - Show the bot command menu. / Afișează meniul de comenzi.
- `/ping` - Check the bot gateway latency. / Verifică latența gateway a botului.
- `/server` - Show server information and statistics. / Afișează detalii și statistici despre server.
- `/avatar` - Show your avatar, a server member's avatar, or any user's avatar by Discord ID. / Afișează avatarul tău, al unui membru sau al oricărui utilizator după ID.
- `/poll` - Create a quick yes/no poll with emoji reactions. / Creează rapid un sondaj da/nu cu reacții.
- `/roll` - Roll dice using formats like `1d6` or `2d20` (Supports up to 20d1000). / Aruncă zaruri în format `1d6` sau `2d20`.
- `/coinflip` - Flip a coin (Returns "Cap" or "Pajura" for slash command). / Aruncă o monedă (Returnează „Cap” sau „Pajura” pentru comanda slash).
- `/choose` - Let the bot choose from comma-separated options. / Lasă botul să aleagă dintr-o listă de opțiuni separate prin virgulă.

### Utilities & Tracking / Utilitare și Monitorizare

- `/whoisuser` - Show detailed info about a Discord user by member, ID, or username. / Afișează detalii despre un utilizator Discord după membru, ID sau username.
- `/whois` - Look up information about a public IP address via ipinfo.io. / Caută informații despre o adresă IP publică prin ipinfo.io.
- `/pingip` - Ping an IP address using the local system ping command to check status. / Dă ping unei adrese IP folosind comanda locală din sistem pentru a verifica starea.
- `/loltrack` - Track a League of Legends summoner profile (Rank, LP, Win/Loss, KDA) using op.gg data. / Monitorizează un profil de League of Legends (Rank, LP, W/L, KDA) folosind date op.gg.

### Moderation / Moderare (Requires Permissions)

- `/purge` - Delete 1-100 recent messages in the channel. / Șterge între 1 și 100 de mesaje recente din canal.
- `/slowmode` - Set or disable this channel's slowmode delay (0 to 21600 seconds). / Setează sau dezactivează slowmode pentru canalul curent.
- `/lock` and `/unlock` - Toggle message-sending permissions for the default role (`@everyone`). / Blochează sau deblochează dreptul de a scrie pe canal pentru rolul implicit.
- `/timeout` and `/untimeout` - Manage member timeouts with custom duration and reasons. / Gestionează timeout-urile membrilor cu durată și motiv personalizat.
- `/kick`, `/ban` - Kick or ban members with safe hierarchy checks. / Dă afară sau banează membri, cu verificări sigure de ierarhie a rolurilor.
- `/unban` - Unban a user from the server using their Discord user ID. / Revocă banul unui utilizator folosind ID-ul de Discord.

---

## Mention Commands / Comenzi prin mențiune

Most commands can also be executed by mentioning the bot directly in chat: / Majoritatea comenzilor funcționează și dacă menționezi botul direct în chat:

```text
@bot help
@bot ping
@bot server
@bot avatar
@bot avatar @user
@bot avatar 123456789012345678
@bot userinfo @user
@bot poll Should we play tonight?
@bot roll 2d20
@bot coinflip
@bot choose pizza, sushi, tacos
@bot whois 1.1.1.1
@bot pingip 8.8.8.8
@bot loltrack SummonerName euw
@bot purge 10
@bot slowmode 5
@bot lock raid cleanup
@bot unlock done
@bot timeout @user 10 spam
@bot untimeout @user
@bot kick @user reason
@bot ban @user reason
@bot unban 123456789012345678 reason
