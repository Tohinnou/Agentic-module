# Notes d'apprentissage — Marina Rentals Sandbox

> **But** : tes notes mentales sur les idiomes/pièges rencontrés en codant.
> **Pourquoi pas en commentaires ?** CLAUDE.md §"Doing tasks" : pas de commentaires qui expliquent le WHAT (les noms le font déjà). Tes notes sont pédagogiques — elles n'appartiennent pas au code source.
> **Convention** : 1 section par phase, 1 sous-section par fichier touché.

---

## Phase 1 — Mise en place du projet

### `src/sandbox/api.py`

**`@asynccontextmanager` (de `contextlib`)** : transforme une fonction asynchrone avec `yield` en gestionnaire de contexte asynchrone. FastAPI s'en sert pour le pattern `lifespan` (remplaçant moderne de `@app.on_event("startup")`, deprecated depuis FastAPI 0.93).
- Code **avant** `yield` = startup (ex : `init_db()`)
- Code **après** `yield` = shutdown (ex : fermer un pool de connexions)

---

### `src/sandbox/db.py`

**`connect_args={"check_same_thread": False}`** : SQLite refuse par défaut qu'une connexion soit partagée entre threads. FastAPI étant multi-thread, sans ce flag tu auras `ProgrammingError: SQLite objects created in a thread can only be used in that same thread`.

**`autoflush=False, autocommit=False`** : tu décides quand committer. Sans ça, un `session.query(...)` peut déclencher un flush implicite d'objets half-built et te donner des erreurs cryptiques.

**`init_db()`** : crée le dossier `data/` et toutes les tables. Idempotent (= safe à rappeler). `Base.metadata.create_all(engine)` regarde toutes les sous-classes de `Base` qui ont été importées et crée les tables manquantes.

**`get_db()`** : générateur (pas une fonction normale). FastAPI le détecte et l'utilise comme **Dependency Injection** : `def endpoint(db: Session = Depends(get_db))`. Le `finally: db.close()` garantit qu'on ne fuit pas de connexions, même si l'endpoint lève une exception.

---

### `src/sandbox/models.py`

**SQLAlchemy 2.0 vs 1.x** :
- `DeclarativeBase` (subclassing) remplace `declarative_base()` (factory)
- `Mapped[str]` + `mapped_column(...)` remplace `Column(...)` → type checking statique + IDE plus malin
- `String(36)` car un UUID canonique fait 36 caractères (`8-4-4-4-12` + tirets)

**Piège du `default=`** : `default=lambda: str(uuid.uuid4())` (avec lambda) → évalué à chaque insert. `default=str(uuid.uuid4())` (sans lambda) → évalué UNE fois à l'import → tous les tickets auraient le même UUID.

**`server_default=func.now()`** : c'est SQLite qui pose le timestamp, pas Python. Source unique de vérité, pas de skew entre serveurs/threads.

---

### `tests/test_health.py`

**`TestClient` (Starlette)** : wrapper synchrone qui simule des requêtes HTTP sans démarrer uvicorn. Rapide, isolé. Dépend de `httpx` (à installer explicitement depuis FastAPI ≥0.110 — ne plus bundlé).

**Pourquoi 2 tests séparés (pas 1 mégatest)** : si tu casses l'endpoint, le test d'import passe quand même → diagnostic instantané.

**Lifespan en test** : `TestClient(app)` déclenche le `lifespan` → `init_db()` crée `data/sandbox.db` pendant pytest. Pour isoler les tests Phase 2+, utiliser une fixture avec `sqlite:///:memory:`.

---

## Phase 2 — Tools agentic (MCP-style)

### Architecture transversale des tools

**Pattern à 4 éléments** que chaque tool doit suivre :
1. `InputModel(BaseModel)` — validation Pydantic à la frontière
2. `OutputModel(BaseModel)` — contrat de retour
3. `def tool(payload: InputModel) -> OutputModel` — la logique
4. `TOOL_METADATA = {...}` dict — contrat MCP exporté (nom, description, risk_level, JSON schemas)

**Séparation `tools/` vs `retrieval/`** : `tools/` contient les wrappers agentic (validation + contrat MCP), `retrieval/` contient les algos purs (BM25, TF-IDF, chunking). Logique : un tool peut être réécrit (changer d'algo) sans toucher au contrat ; un algo peut être réutilisé par plusieurs tools.

**Read/Draft/Act ladder** (CLAUDE.md §7) : `risk_level` détermine le niveau de durcissement du harness.
- `read` = lecture pure, pas de Vibe Diff requis
- `draft` = montre au humain avant envoi
- `act` = approbation explicite + audit

---

### Concept transversal — Qu'est-ce qu'un index ?

**Définition simple** : structures de données précalculées et stockées en mémoire qui transforment une question lente en lookup rapide. Rien de magique — juste des dicts/listes Python cachés dans des attributs.

Pour notre `BM25Index` : 7 attributs (`docs`, `n`, `doc_tokens`, `doc_lengths`, `avgdl`, `doc_freqs`, `idf`). Quelques Ko pour 10 docs.

**Trade-off central** : tu payes (a) du temps de construction au démarrage et (b) de la RAM, en échange de queries rapides. Rentable au-delà de quelques queries.

**Types d'index** :
- **Forward index** (le nôtre) : `doc → {term: freq}`. OK à 10 docs (on score tous les docs).
- **Inverted index** (Lucene, Elasticsearch) : `term → [(doc_id, freq, positions)]`. Pour 100k+ docs : on ne regarde que les docs qui contiennent au moins un terme de la query.
- **Vector index** (FAISS, ChromaDB, pgvector) : `doc → embedding [768 floats]`. Pour recherche sémantique — query aussi embedded, voisins en distance cosinus. C'est ce qu'on ajoutera Phase 5+ (Option C validée).

**Staleness** : si le corpus change, l'index est stale → rebuild nécessaire. D'où le pattern `_INDEX: BM25Index | None = None` + `_get_index()` (lazy + cached).

---

### `src/sandbox/retrieval/corpus.py`

**`@dataclass(frozen=True)`** : immutable + hashable, ~3 lignes vs Pydantic ~10. C'est une donnée **interne** au pipeline → pas besoin de validation runtime. Pydantic c'est pour les **frontières** (I/O API, I/O tool).

**`path.stem`** : `"cancellation_policy.md"` → `"cancellation_policy"`. Identifiant stable et lisible, sert de clé partout en aval.

**`sorted(...glob(...))`** : sans `sorted()`, `glob()` retourne dans un ordre OS-dependent → tests BM25 flaky (mêmes hits, ordre différent selon la machine).

**`encoding="utf-8"`** : Windows défaut = `cp1252` → casse les accents français des docs. Explicite = pas de surprise.

**`Path(__file__).resolve().parents[3] / "docs"`** : robuste vs `Path("docs")` qui est CWD-relatif (footgun rencontré au REPL). `__file__` = chemin du source, `.resolve()` = canonique, `.parents[3]` remonte 3 niveaux (`retrieval` → `sandbox` → `src` → `kaggle`). Trade-off : couplé à la structure des dossiers — si tu déplaces le fichier, faut ajuster `[3]`.

---

### `src/sandbox/retrieval/bm25.py`

**Formule Okapi BM25** :
```
score(D, Q) = Σ  IDF(qᵢ) · (tf · (k₁+1)) / (tf + k₁ · (1 - b + b · |D| / avgdl))
```
- `tf` = fréquence du terme dans le doc
- `|D|` = longueur du doc en tokens, `avgdl` = longueur moyenne du corpus
- `k₁` = saturation TF (1.2–2.0 typique), `b` = normalisation par longueur (0 = aucune, 1 = totale)
- `IDF = log(1 + (N - df + 0.5) / (df + 0.5))` — smoothing Robertson-Spärck Jones

**`K1=1.5, B=0.75`** : valeurs standard Lucene/Elasticsearch. Tuner plus tard.

**`+0.5` dans l'IDF** : **smoothing Robertson-Spärck Jones**. Évite `log(0)` quand un terme apparaît dans tous les docs (sinon IDF négative) et adoucit l'IDF des termes rares.

**`re.findall(r"\b\w+\b", text.lower())`** : tokenizer simple. `\w+` = lettres/chiffres/_, `\b` = word boundary. Gère les accents FR en Unicode par défaut (Python 3). **Pas de stemming** → "annulation" ≠ "annuler". OK pour sandbox ; en prod : Snowball-fr.

**Pas de stopword filter** : BM25 le fait naturellement via l'IDF — "le", "de", "et" apparaissent partout → IDF ≈ 0 → contribution nulle au score.

**Tout en mémoire** (`self.doc_tokens`, `self.doc_freqs`) : 10 docs = quelques Ko. Pour 10k+ docs tu passerais à un index sur disque (Whoosh, Tantivy).

**`Counter` au lieu de `dict`** : dict spécialisé pour le comptage. `Counter(["a","b","a"])` → `{"a":2,"b":1}` en une ligne.

**Sort puis slice** vs `heapq.nlargest` : à 10 docs c'est invisible. À 100k tu utiliserais `heapq`.

**Tri stable + ex æquo** : `list.sort` Python est stable → si 2 docs ont le même score, l'ordre d'insertion est préservé. Comme `corpus.py` retourne déjà les docs triés alphabétiquement par `doc_id`, les ex æquo sont résolus alphabétiquement. **Tests reproductibles.**

**Underscore préfixe** (`_score`, `_compute_idf`) : convention Python pour "privé" — signal aux lecteurs, pas enforced par le langage.

---

### `src/sandbox/tools/retrieve_docs.py`

**`Field(..., min_length=1)`** : `...` = requis sans défaut. `min_length=1` rejette `query=""` au runtime Pydantic — l'erreur arrive à la frontière, pas dans `BM25Index.query` 3 niveaux plus bas.

**`top_k: int = Field(3, ge=1, le=10)`** : default + bornes. Sans `le=10`, un LLM pourrait demander `top_k=99999` et tu lirais tout le corpus. **Règle générale** : toujours borner les inputs LLM.

**`payload` au lieu de `input`** : `input` shadow le builtin Python `input()` → bug muet. Conventions : `payload`, `args`, `req`.

**Lazy init du `_INDEX`** (`_INDEX: BM25Index | None = None` + `_get_index()`) : on ne construit l'index qu'au premier appel, pas à l'import. Tests qui mockent le corpus ne payent pas le coût d'indexation à chaque import.

**Underscore préfixe module-level** (`_INDEX`, `_get_index`) : privé module-level, n'utilise pas depuis l'extérieur.

**`snippet=doc.content[:200]`** : on retourne un aperçu, pas le doc entier. Raisons : (1) limiter le contexte injecté dans le LLM downstream (token budget), (2) forcer l'agent à demander le doc complet via un autre tool s'il en a besoin (Read minimal vs Read full).

**`TOOL_METADATA` dict séparé** : contrat **public** du tool — nom, description, risk_level, JSON schemas. Le registry Phase 2 lira ce dict pour générer `meta/tool_registry.json`. **Une seule source de vérité : le code.**

**`description` détaillée avec scénario** : CLAUDE.md §5 — la description est la **router function**, elle dit **quand** invoquer le tool, pas juste **ce qu'il fait**. C'est elle qui décide si l'agent l'appelle.

**`risk_level: "read"`** : niveau Read du Read/Draft/Act ladder. Pas de Vibe Diff, pas de Semantic Gating obligatoire — lecture pure.

**`model_json_schema()`** : Pydantic v2 génère le JSON Schema standard à partir du BaseModel → compatible MCP / OpenAI function calling **sans réécrire à la main**.

---

### `tests/test_retrieve_docs.py`

**3 tests, 1 invariant chacun** : si un test casse, le nom dit immédiatement quoi est cassé (shape ? pertinence ? top_k ?). Vs mégatest → tu lis 30 lignes pour comprendre.

**`isinstance(out, RetrieveDocsOutput)`** : garantit que le retour est bien la Pydantic Output, pas un dict accidentel. Protège du refactor sournois.

**Le test de pertinence (`cancellation_policy`) est le seul qui teste vraiment BM25** : les 2 autres testent le **contrat Pydantic**. Si demain tu remplaces BM25 par TF-IDF ou semantic search, ce test doit toujours passer — il valide le **comportement attendu**, pas l'algo. Pattern fondamental EDD.

**Pas de mock du corpus** : on teste contre le vrai corpus de 10 docs. ~50ms, c'est rapide. À 10k docs on mocquerait un mini-corpus de fixtures.

**Score ≥ 0 (pas == X.XX)** : on teste les **invariants** (positifs, ordre), pas des valeurs exactes — sinon le test casse à chaque tweak de constante.

**Pas de test pour `query=""` ou `top_k=99`** : ça testerait **Pydantic**, pas notre code. **Règle générale** : teste **ton** code, pas tes dépendances.

**État global `_INDEX` et isolation** : les 3 tests partagent le même index une fois construit. OK ici (tout est read-only, personne ne mute `_INDEX`). Si un jour un test modifie le corpus → fixture pytest :
```python
@pytest.fixture(autouse=True)
def reset_index(monkeypatch):
    monkeypatch.setattr("sandbox.tools.retrieve_docs._INDEX", None)
```
À ajouter quand le besoin se présente (YAGNI).

---

### `src/sandbox/classification/rules.py`

**Pourquoi pas de stemming ni de normalisation d'accents** : on encode directement les variantes dans les sets de keywords (`"tempête"` + `"tempete"`, `"sécurité"` + `"securite"`). Plus simple, plus explicite, plus rapide à debugger. Coût : maintenance manuelle. En prod : Snowball-fr + `unicodedata.normalize("NFD", ...)`.

**`Literal[...]` types Python → JSON Schema `enum`** : Pydantic v2 sérialise automatiquement `Literal["urgent","high","normal","low"]` en `"enum": [...]` dans le JSON Schema. Quand un LLM appellera le tool, le contrat MCP exposera `priority` comme enum à 4 valeurs et le modèle ne pourra pas inventer `"very_urgent"`. **Single source of truth** : le typage Python EST le contrat MCP.

**Tokenize footgun `aujourd'hui`** : `re.findall(r"\b\w+\b", text.lower())` casse l'apostrophe → `["aujourd", "hui"]`. On garde `"aujourd"` comme keyword TIME_PRESSURE parce que c'est le segment **stable** (toujours présent qu'on écrive "aujourd'hui", "aujourdhui" ou "aujourd hui"). Alternative rejetée : pré-traiter le texte pour normaliser les apostrophes — ajoute une surface d'erreur.

**Pattern à 2 axes (catégorie × modificateur de sévérité)** : au lieu d'une table à 8 catégories × 4 priorités = 32 cases, on superpose des règles. `safety → urgent` (dure), `damage` ou `weather` modifiés par `URGENCY_KEYWORDS`, `cancellation` modifié par `TIME_PRESSURE_KEYWORDS`. **Avantage** : ajouter une catégorie = ajouter UNE règle, pas 4 cases. **Trade-off** : moins exhaustif, mais lisible.

**`compute_priority` comme fonction de décision pure** : extraite de `classify_text` → testable en isolation. Pattern général : sépare la **décision** (logique métier) de la **collecte des inputs** (tokenization, scoring). Bonus : si Phase 5 on ajoute un LLM-classifier en parallèle, on peut comparer `compute_priority(rules)` vs `compute_priority(llm)` sur les mêmes inputs.

**Set intersection truthy idiom** : `text_tokens & URGENCY_KEYWORDS` est truthy si non vide. Plus court et **plus rapide** que `any(t in URGENCY_KEYWORDS for t in text_tokens)` — l'intersection se fait en C dans CPython.

**Tie-breaking par dict insertion order** : `max(scores, key=...)` renvoie la **première** clé en cas d'égalité (Python 3.7+ garantit l'ordre d'insertion des dicts). Donc l'ordre dans `CATEGORY_KEYWORDS` détermine qui gagne en cas de tie. Implicite — à documenter ici, ou à remplacer par une règle explicite (`safety > damage > weather > ...`) en prod.

**Defensive fallback explicite** (`if scores[top_cat] == 0: top_cat = "other"`) : `max` sur un dict non-vide ne renvoie jamais `None` — il renverra la première clé avec score 0. Sans le check, un texte sans aucun keyword serait classé "cancellation" (première du dict). Le test `== 0` rend l'intention claire : "si rien ne matche, on tombe sur 'other'".

**`sorted(token_set & kws)`** : `set` itère dans un ordre **non-déterministe** entre runs (hash seed). Stocker un set non trié dans `matched_keywords` → tests flaky. `sorted()` garantit alphabétique → reproductibilité.

**Laplace-style smoothing dans `confidence`** : `scores[top_cat] / (total + 1)` au lieu de `/ total`. Le `+1` empêche `confidence == 1.0` même quand toutes les hits tombent dans une seule catégorie. Sémantique : "il reste toujours une chance résiduelle qu'on ait raté quelque chose". Évite l'overconfidence — important pour la suite quand on ajoutera un LLM-judge.

**Pourquoi `confidence` est calculée DANS chaque branche du `if/else`** : la première version avait `confidence = scores[top_cat] / (total + 1) if scores[top_cat] > 0 else 0.0` **après** le if/else → KeyError parce que `top_cat = "other"` mais `"other"` n'est pas dans `scores` (CATEGORY_KEYWORDS n'a que 7 catégories). Restructure : chaque branche calcule sa propre confidence → pas de défensive code (`.get(...)`), chaque branche est self-contained. **Règle générale** : si un `if/else` produit déjà la valeur correcte pour chaque cas, ne rajoute pas un calcul "commun" après qui doit re-checker l'état.

---

### `src/sandbox/tools/classify_ticket.py`

**`Literal` réutilisé comme type Pydantic** : `Category` et `Priority` viennent de `rules.py` → JSON Schema `enum` automatique dans le contrat MCP. Pas de réécriture, pas de drift entre la logique et le contrat publié.

**Tool = wrapper, rules = pure logic** : même séparation que `retrieve_docs` / `bm25`. Le tool valide l'input (Pydantic), appelle la logique, valide l'output. Si Phase 5 on remplace `classify_text` par un LLM, le tool ne change pas — seule l'impl change.

**Pas de `_INDEX` lazy init** (contrairement à `retrieve_docs`) : la classification est **stateless** — aucune structure précalculée. Tokenize + dict lookups, c'est tout. Pas besoin du pattern lazy/cached.

**`description` exhaustive avec listes** : on liste explicitement les 8 catégories et 4 priorités. CLAUDE.md §5 : la description est la **router function** — un LLM la lit pour décider d'invoquer le tool. Plus c'est concret (listes explicites des valeurs renvoyées), plus le routing en aval sera précis.

---

### `tests/test_classify_ticket.py`

**4 tests, 4 invariants** : shape, routing (cancellation+high), escalation (safety→urgent), fallback (other+low). Si un test casse, le nom dit immédiatement quoi.

**Tests via le wrapper, pas via `compute_priority`** : on cible `classify_ticket` (surface publique), pas les fonctions internes. EDD : si demain on remplace l'implémentation par un LLM, les tests restent valides — ils valident le **comportement**, pas l'algo.

**Le cas `"Bonjour"` régression-proofé** : ce texte exact a déclenché 3 bugs successifs pendant l'écriture de `classify_text` (TypeError sur le `None` implicite, UnboundLocalError sur `priority`, KeyError sur `"other"`). Le test verrouille les 4 assertions (`category=="other"`, `priority=="low"`, `confidence==0.0`, `matched_keywords==[]`) → impossible de re-régresser silencieusement.

**`"annuler" in out.matched_keywords`** plutôt que `== ["annuler"]` : tolérant. Si on ajoute des keywords ou si le tokenizer évolue, le test reste vert tant que l'essentiel est là.

**Pas de test direct des sets `URGENCY_KEYWORDS` / `TIME_PRESSURE_KEYWORDS`** : ils sont testés *en passant* (`test_cancellation_routing` teste TIME_PRESSURE, `test_safety_escalates_to_urgent` teste URGENCY). Pas la peine de dupliquer.

---

### `src/sandbox/drafting/templates.py`

**Pourquoi un package `drafting/` séparé de `tools/`** : même pattern que `bm25.py`/`retrieve_docs.py` et `rules.py`/`classify_ticket.py` — logique pure d'un côté (`drafting/templates.py`), wrapper MCP de l'autre (`tools/draft_reply.py`). Si demain on remplace les templates statiques par un LLM ou par Jinja2, **seul `templates.py` change**, le wrapper reste stable.

**`Path(__file__).parent / "templates"`** (vs `parents[3]` dans `corpus.py`) : les templates sont **in-package** (livrés avec le code), pas dans un dossier-data à la racine du projet. Pas besoin de remonter à `kaggle/`, on reste collé au module. Avantage : si on package le projet en wheel, les `.txt` voyagent avec.

**Regex `\[\[[A-Z_]+\]\]` strict (uppercase + underscore)** : défensif — rejette les "faux placeholders" minuscules ou mixed-case (ex : `[[Name]]`, `[[user_name]]`). Force la convention Context Hygiene à être respectée à l'écriture des templates. Si un dev tape `[[booking_id]]`, le regex ne le capte pas → bug visible immédiatement à l'eval, pas en prod.

**`sorted(set(...))` — dedup + ordre déterministe** : un placeholder comme `[[CUSTOMER_NAME]]` apparaît plusieurs fois dans un template (en haut + en bas). `set` retire les doublons ; `sorted` impose l'alphabétique stable (sinon `set` itère selon le hash seed → tests flaky entre runs). **Même idiome que `sorted(token_set & kws)` dans `rules.py`** — pattern réutilisable.

**`select_tone` = fonction de décision pure** (même pattern que `compute_priority`) : testable en isolation, swappable. Si Phase 5 on ajoute un LLM-tone-selector en parallèle, on peut comparer `select_tone(rules)` vs `select_tone(llm)` sur les mêmes inputs.

**Ordre des `if` dans `select_tone`** :
1. `safety` override absolu — vie humaine prime sur tout (priority pas regardée)
2. `priority == urgent` override — applique à damage/weather urgents
3. Set explicite `{cancellation, payment, booking}` → `formal` — transactions business
4. Fallback `neutral` — tout le reste (`other`, `equipment`, `damage`/`weather` non urgents)

**Pourquoi un set explicite et pas un fallback à `formal`** : `formal` n'est PAS la valeur sûre par défaut. Un message sur un kayak cassé doit avoir un ton `neutral` (technique, informatif), pas `formal` (notarial). Lister les 3 catégories transactionnelles évite le sur-formalisme.

**`Tone = Literal[...]`** (et pas `Enum`) : SSOT — Pydantic transforme automatiquement en JSON Schema `enum`. Pas de classe à définir, pas de `.value` à invoquer côté code. Même approche que `Category`/`Priority`.

---

### `src/sandbox/tools/draft_reply.py`

**Pas de `customer_message` en input** — Defense in depth contre le PII-leak : si le tool **ne peut pas recevoir** le message client brut (qui contient potentiellement nom, email, n° de carte, photo de pièce d'identité…), alors il **ne peut pas accidentellement le logger** dans la Vibe Trajectory. Règle : le PII ne franchit pas la frontière du tool. La classification (`category`, `priority`) et le doc cité (`policy_doc_id`) suffisent pour générer le template. Si plus tard on a besoin du message original (ex : citation littérale), on passe par un autre tool qui redacte avant de logger.

**`policy_doc_id` (ID), pas le contenu du doc** : audit trail propre (`cited_policy_id` passthrough en output) + ne pollue pas le contexte LLM downstream. L'ID est court, stable, traçable.

**`risk_level="draft"` (premier non-read)** : la sortie **doit** être relue par un humain avant envoi (placeholders à remplir, ton à valider). Le tool lui-même n'a pas de side-effect (rien n'est envoyé). Pattern Read/Draft/Act :
- Read = lecture pure (`retrieve_docs`, `classify_ticket`)
- Draft = génère un artefact qui requiert validation humaine avant action (`draft_reply`)
- Act = exécute une action irréversible (à venir : `create_ticket`, `send_reply`)

**`description` qui encode l'ordre de la chain** ("À utiliser APRÈS classify_ticket et retrieve_docs, AVANT tout tool d'envoi") : la description est la **router function** lue par le LLM agent. En écrivant les dépendances ordonnées, on **enseigne au modèle** comment composer la chaîne sans qu'il ait à le deviner.

**`cited_policy_id` passthrough (pas régénéré)** : l'ID du doc qui a justifié la classification reste **attaché** au draft. Sans ça, lors d'une review on ne saurait plus *pourquoi* ce template a été choisi. C'est la **DNA de la décision** — chaque draft connaît la politique qui l'a généré.

**Délégation pure à `templates.py`** : le tool ne contient **aucune** logique métier — juste wrapping Pydantic + 3 appels (`load_template`, `extract_placeholders`, `select_tone`). Réécriture future = changer `templates.py`, le tool reste stable.

**Mention explicite "HITL" dans la description** : prévient l'Approval Fatigue théâtre. Sans cette mention, un orchestrateur pourrait enchaîner `draft_reply` → `send_reply` sans pause humaine. La description force l'arrêt entre les deux.

---

### `tests/test_draft_reply.py`

**5 tests, 5 invariants** : shape (Pydantic), routing du ton (4 branches), extraction des placeholders (dedup + tri), fallback `other`, métadonnée TOOL_METADATA. Même discipline qu'`test_classify_ticket.py`.

**Pourquoi 4 cases dans `test_tone_routing`** : couvre les 4 branches de `select_tone` — override safety (peu importe la priority), override priority urgent (sur damage), set formal explicite (cancellation), fallback neutral (equipment). Si quelqu'un réordonne les `if` ou retire une catégorie du set formal, **au moins un cas casse**.

**Assertion `out.placeholders == sorted(set(out.placeholders))`** : verrouille **explicitement** le contrat Context Hygiene (dedup + tri). Sans cet invariant, quelqu'un pourrait retirer `sorted(set(...))` et renvoyer la liste brute du regex (avec doublons et ordre du texte) → tests d'égalité passent par chance, contrat invisible cassé.

**Test du fallback `other`** : protège contre la suppression accidentelle de `other.txt` (sinon `FileNotFoundError` muet en prod) ET valide que la branche `neutral` est bien atteinte. Régression à coût zéro.

**`<=` (subset) sur `set(in_props.keys())` et pas `==`** : Pydantic ajoute parfois des champs internes au JSON Schema (`additionalProperties`, `title`, etc.) selon la version. Asserter l'égalité stricte rendrait le test fragile aux upgrades. On vérifie que **nos** champs sont là, pas qu'il n'y en a aucun autre.

**`test_tool_metadata_shape`** : `TOOL_METADATA` est le contrat consommé par le futur Policy Server (Structural Gating) et l'AgBOM (signature). Un typo dans un nom de champ casse silencieusement la chain — d'où le test sur les clés exactes (`name`, `risk_level`, `input_schema`, `output_schema`).

---

## Phase 3 — *(à compléter)*
