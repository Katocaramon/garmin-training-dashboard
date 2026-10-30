# Garmin Dashboard

Una dashboard personale dei propri allenamenti, costruita con la **Garmin Personal API** ufficiale (sola lettura).
È un unico file HTML che si apre nel browser e funziona anche sul telefono. Mostra:

- il conto alla rovescia per la gara obiettivo e il tempo da battere
- l'HRV in primo piano, con la fascia normale e lo stato
- la settimana in corso confrontata con le 4 settimane precedenti, sport per sport
- gli andamenti di HRV, carico di allenamento, battito a riposo e sonno
- i record di corsa, le uscite più lunghe e le giornate più dure

Serve solo Python 3.10 o più recente. Non ci sono librerie da installare.

## Configurazione

1. Crea una Personal API Key su Garmin Connect:
   [Garmin Developer Program](https://developer.garmin.com/gc-developer-program/overview/) → **Personal** → **Set Up Now**.
2. Copia `.env.example` in `.env.local` e incolla la chiave dopo il segno `=`.
3. Copia `settings.example.json` in `settings.json` e inserisci nome e data della tua gara.

`.env.local`, `settings.json`, `data/` e `dashboard.html` contengono dati personali.
Per questo sono esclusi da git (vedi `.gitignore`).

## Uso

```bash
python3 pull.py --all   # la prima volta: scarica tutto lo storico (senza --all: ultimi 12 mesi)
python3 build.py        # crea dashboard.html
```

Per gli aggiornamenti successivi ci sono due modi:

- `./refresh.sh` scarica solo i dati nuovi e ricostruisce la dashboard.
- Su Mac puoi fare doppio clic su **`Apri dashboard.command`**. Avvia un piccolo server locale
  (`serve.py`, raggiungibile solo da `127.0.0.1`) e così il pulsante **Aggiorna** funziona direttamente
  dalla dashboard.

## File

| File | Cosa fa |
|---|---|
| `garmin_api.py` | Client della Personal API: scambia la chiave con il token, lo salva per 20 ore e gestisce l'errore 401 |
| `pull.py` | Scarica attività, riepiloghi giornalieri, sonno, HRV e peso in `data/`. È incrementale e riprende da dove si era fermato |
| `build.py` + `template.html` | Generano `dashboard.html` con i dati incorporati e grafici in SVG puro |
| `serve.py` | Server locale per il pulsante Aggiorna |
