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

### `src/sandbox/models.py` — refonte Tool 4 (Ticket schema v2)

**Suppression de `customer_email` et `message` (Q1 defense in depth)** : Phase 1 avait un stub PII-friendly. Pour Tool 4, on a explicitement retiré ces 2 colonnes. Logique : la PII doit vivre dans la trajectoire (audit, accès contrôlé), **pas** dans la table `tickets` consultée régulièrement par les agents. Si un dev se trompe (`UPDATE tickets SET ... pour exfiltrer`), il ne trouve rien d'identifiant. Défense en profondeur — la PII absente au niveau colonne est impossible à fuiter par cette colonne.

**`status` default `"new"` (pas `"open"`)** : "open" est ambigu (créé ? assigné ? en cours ?). "new" = explicite, dénote l'absence de tout traitement. Machine d'états future (new → assigned → in_progress → resolved → closed) plus claire à partir de "new".

**`cited_policy_id` nullable** : "other" et certains edge cases peuvent ne pas avoir de policy citée. NOT NULL aurait forcé l'agent à inventer un ID factice ("MR-OTHER-2024-X") → cargo cult. Nullable = honnête sur le fait que l'audit trail peut être vide dans certains cas légitimes.

**`draft_text: Mapped[str | None]` + type SQL `Text`** : `Text` (pas `String(N)`) parce qu'un draft peut faire plusieurs paragraphes. `Mapped[str | None]` (syntaxe Python 3.10+) = SQLAlchemy 2.0 infère `nullable=True` du `| None` automatiquement. On garde `nullable=True` explicite dans `mapped_column(...)` quand même — les futurs lecteurs n'ont pas à connaître la magie SQLAlchemy 2.0.

**`idempotency_key: nullable=True, unique=True`** : nullable parce que beaucoup d'appels n'auront pas de clé (mode "fire and forget"). Unique parce que **quand il y en a une, elle garantit l'unicité**. SQLite traite `NULL` comme **distinct** dans un unique index → on peut avoir 1000 lignes avec `NULL` sans violation. Si la DB voit deux INSERT avec la même clé non-NULL → `IntegrityError`. **Atomique au niveau DB** — pas de race condition Python.

**Pourquoi pas `sqlalchemy.Enum` pour `category` / `priority` / `status`** : SQLite n'a pas d'enum natif. SQLAlchemy traduit en CHECK constraint, mais ALTER est limité en SQLite (recréer la table à chaque ajout). Trade-off accepté : on valide côté Pydantic (Literal) au boundary du tool. **Assomption** : create_ticket est le seul writer → catégorie invalide ne peut jamais arriver en DB. Le coût d'une migration future Postgres (où Enum est plus naturel) reste contenu.

**`server_default=func.now()` (pas `default=datetime.now`)** : `func.now()` exécuté **côté SQL** par la DB. Avantage : tous les processus voient la même horloge (celle de la DB). Avec `default=datetime.now` côté Python, deux serveurs avec des horloges légèrement désynchronisées produiraient des timestamps incohérents pour des INSERT concurrents.

---

### `src/sandbox/tools/create_ticket.py`

**`risk_level: "act"` — premier tool de ce niveau** : ladder Read / Draft / Act du cours (Day 5). Read = pure lecture. Draft = génère sans envoyer. Act = effet de bord persistant ou externe (DB, email, paiement). `act` impose : Vibe Diff pré-action (résumé humain pré-exécution) + Vibe Trajectory post-action (audit). Le Policy Server (Phase 4) liera `risk_level=act` au pattern HITL automatiquement.

**Pattern "try INSERT, except UNIQUE" (pas "SELECT then INSERT")** : pattern industriel (Stripe, Twilio). Le "check then insert" introduit une race condition (deux requêtes concurrentes voient "absent" en même temps). L'unique index DB est **atomique**. On essaie d'insérer ; si UNIQUE est violé → on lit l'existant. Aucune fenêtre de course possible.

**`if payload.idempotency_key is None: raise`** : si IntegrityError survient sans clé d'idempotency, c'est forcément autre chose (NOT NULL violation, etc.). On ne doit pas avaler silencieusement — on re-raise. Avantage vs string-match sur le message d'erreur SQLite : portable entre dialectes (SQLite, Postgres, MySQL formulent l'erreur différemment).

**Séparation 2 paramètres : `payload` (Pydantic) + `db_session` (SQLAlchemy)** : c'est concrètement le **Zero Ambient Authority** au niveau Python. Le tool ne va pas chercher la DB tout seul (pas de `SessionLocal()` global) — la session est **injectée** par le caller. Conséquences : (1) le contrat MCP n'expose que `payload`, pas la session, (2) on peut injecter une session de test (in-memory), de prod (file DB), ou DI FastAPI (`Depends(get_db)`) sans toucher au tool.

**`session.rollback()` AVANT le `select` dans except** : indispensable. Une session avec une transaction en erreur ne peut plus exécuter de query — le `select` lèverait `InvalidRequestError`. Le `rollback` nettoie la transaction → la query suivante part sur une session saine.

**`session.refresh(ticket)` après commit** : recharge l'objet depuis la DB pour récupérer les valeurs **générées server-side** : `created_at` (via `func.now()`). Sans `refresh`, `ticket.created_at` est `None` côté Python jusqu'à la prochaine query.

**Drapeau `idempotency_replay: bool` dans l'output** : sans ce drapeau, l'appelant ne saurait pas si son INSERT a vraiment écrit ou s'il a juste relu un ticket existant. Le Policy Server / la trajectory peuvent logger différemment (vrai INSERT = action ; replay = no-op observable). C'est de l'**observabilité au niveau du contrat de retour**.

**Absence intentionnelle de `body` / `message` / `customer_email` dans `CreateTicketInput`** : régression Q1 explicite côté contrat MCP. Si l'input acceptait `body`, le contrat **annoncerait** au LLM agent "tu peux passer le message client ici" → fuite intentionnelle. La PII se loggue dans la trajectory côté caller, pas dans le tool.

**`description` du TOOL_METADATA encode `ATTENTION (risk_level=act)`** : pour que le LLM agent qui lit la doc du tool comprenne **pourquoi** ce tool est spécial — pas juste un INSERT comme un autre. Pédagogique pour le modèle lui-même, en plus du Policy Server.

---

### `tests/test_create_ticket.py`

**Fixture `db_session` avec `StaticPool`** : piège SQLAlchemy classique. Par défaut, chaque nouvelle connexion à `sqlite:///:memory:` crée une **nouvelle DB vide** (la mémoire est isolée par connexion). `StaticPool` force une connexion unique partagée → la DB persiste pendant le test. Sans ça : l'INSERT et le SELECT suivant ne voient pas la même DB → tests qui passent en mode mock et castent en vrai.

**Fixture per-test (pas `scope="module"`)** : isolation totale. Un test qui INSERT n'affecte pas le test suivant. Coût négligeable (in-memory, ~800ms total pour 9 tests). Trade-off : fidélité d'isolation > vitesse marginale.

**Factory `_valid_input(**overrides)`** : DRY. 9 tests qui ont besoin d'un payload valide → 1 endroit central. `**overrides` = chaque test ne surcharge que ce qu'il teste **spécifiquement** → lisibilité (on voit immédiatement le delta par rapport au baseline).

**Assertion `count == 1` après replay** : sans cet assert, on pourrait croire que "replay" = "renvoyer le même ID en RAM" alors qu'en réalité on aurait pu créer 2 lignes (le test ne le verrait pas). L'assert ferme cette possibilité. La vérité est en DB, pas dans l'objet retourné.

**Test "pas d'idempotency_key = 2 ticket_id différents"** : verrouille la sémantique. On ne fait **pas** d'idempotence "magique" basée sur le hash du payload (Stripe ne le fait pas non plus). Idempotence = explicite via clé fournie. Sans ce test, quelqu'un pourrait ajouter un "smart hashing" sans le savoir et casser le contrat documenté.

**`test_no_pii_columns_in_ticket_schema` (régression Q1 "tatouage")** : inspecte les colonnes effectives du modèle SQLAlchemy. Si quelqu'un (humain, copilot) re-ajoute `customer_email` ou `body` au modèle → test cassé immédiatement, avec un message qui dit exactement pourquoi. La décision Q1 vit dans le code de test, pas juste dans une conversation passée.

**`test_draft_text_with_placeholders_persisted_intact`** : verrouille **Context Hygiene** côté persistance. Si un jour quelqu'un ajoute un helper qui résout `[[CUSTOMER_NAME]]` à `"Jean Dupont"` avant l'INSERT → PII en DB, test cassé. Le helper de résolution est interdit par contrat de test à ce niveau.

**`test_tool_metadata_shape` avec `"body" not in in_props`** : régression Q1 au niveau du contrat MCP exposé. Le test interdit que `body` réapparaisse dans l'input schema. Sans ça, un dev pourrait re-ajouter `body` à `CreateTicketInput` sans le câbler à `Ticket(...)` → contrat MCP qui ment (validate `body` mais le jette silencieusement).

---

### Concept transversal — LLM-as-Judge à 7 dimensions

**Pourquoi 7 dimensions et pas 1 score "qualité"** : un seul score 0-5 mélange tout — un draft poli mais qui ment a "qualité = ?". Trois dimensions (`exactitude`, `ton`, `sécurité`) ratent encore les pathologies fréquentes : un draft correct factuellement mais qui répond à côté (`pertinence`), un draft pertinent mais lourd à lire (`clarté` / `concision`), un draft poli mais qui oublie un élément attendu (`complétude`). 7 dimensions = chaque catégorie d'échec a un signal dédié → debug ciblé au lieu d'un score agrégé inutilisable.

**Orthogonalité (= chaque dimension capte UNE qualité)** : un draft qui ment poliment doit avoir `ton=4` ET `exactitude=1`. Si le juge fusionne (`ton=2` parce que mensonge), il signale **deux** problèmes alors qu'il y en a un. Le cas `cancellation-24-48h-cold-tone-borderline` du golden teste précisément cette séparation : `exactitude=5` (frais 30% correctement appliqués) ET `ton=2` (sec) — le juge doit isoler les axes sans contaminer.

**Buckets `pass` / `fail` / `borderline` (2/2/2)** : un golden 100% `pass` détecte un juge laxiste (il valide tout). 100% `fail` détecte un juge sévère. Que des cas tranchés ne détecte **pas** un juge sans nuance (qui colle 5 ou 0 partout, jamais 3). 6 cas équilibrés en 3 buckets = 3 types de défaillance juge détectés au minimum.

**Tolérance `±1` sur les scores attendus** : le juge LLM reste stochastique même à `temperature=0` (warmup CUDA, batch size, version provider). Asserter `score == 5` exact → calibration cassée à la première mise à jour côté provider. `±1` absorbe la variance naturelle sans laisser passer des dérives à 2 points (qui restent significatives).

**Borne basse `0` réservée aux pathologies critiques** : `exactitude=0` ou `securite=0` ne s'utilise QUE pour les drafts qui contredisent directement la policy ou fuient des données interdites. Sans cette discipline, un juge tendrait vers `0-2` pour tout ce qui n'est pas parfait → écrasement de la nuance basse de l'échelle. Le golden encode cette règle dans les `notes:` de chaque cas pour ancrer le prompt.

---

### Concept transversal — EDD strict pour LLM-as-Judge

**Le golden YAML AVANT le `judge.py`** : CLAUDE.md §6 (Evaluation-Driven Development). Sans golden écrit en amont, on règle le juge sur ses propres outputs → biais de confirmation. Le golden encode des **attentes humaines** indépendantes du modèle. La calibration mesure l'**écart** entre le juge et l'humain — c'est cet écart, pas une accuracy absolue, qui valide ou invalide le juge.

**Itération `v1 → v2` du prompt SYSTEM** : première run avec le prompt v1 → 1/6 cas passent. Le juge interprétait le draft comme une action autonome (alors qu'un humain le valide en HITL) → il sur-pénalisait les engagements ("je procède à l'annulation"). v2 ajoute un bloc `CONTEXTE OPÉRATIONNEL` (le draft est relu par humain, l'agent propose) → calibration passe à 3/6, puis 6/6 après patches du golden. Le prompt n'est jamais "écrit puis figé" — il est un **artefact calibré** contre des cas concrets.

**`PROMPT_VERSION` versionné + injecté dans la clé de cache** : sans version dans la clé, modifier le prompt n'invalide pas le cache → les vieilles notes du prompt v1 persistent et faussent toute calibration future. Bump `v1 → v2` = clé de hash change pour tous les payloads → re-évaluation forcée. Pattern industriel : tout changement de prompt = bump de version, jamais d'édition silencieuse.

**Le juge révèle les bugs DU GOLDEN, pas l'inverse** : lors de l'itération 2 (3/6), les 3 échecs étaient dus à des incohérences internes du golden (cas 1 : "demain 14h" contredit "plus de 48h" dans le draft cité ; cas 2 : client demande si maintenu mais draft confirme annulation comme si Marina avait décidé ; cas 6 : `pertinence=3` incohérent avec la définition v2 "fausse mais SUR LE SUJET = pertinent"). Le `reasoning` du juge LISAIT ces contradictions. Leçon : un juge mal noté n'est pas forcément mauvais — il peut révéler que **mon** golden est buggé. EDD est bidirectionnel.

---

### `evals/judge_golden.yaml`

**Format YAML (pas JSON, pas Markdown brut)** : YAML supporte les blocs `|` literal multi-lignes sans escape → on colle le texte d'un draft de 8 lignes tel quel, indenté, sans cogner des `\n`. JSON aurait imposé `"draft_reply": "Bonjour [[CUSTOMER_NAME]],\nVotre réservation...\n"` → illisible en review. Markdown aurait imposé un parser maison pour extraire la structure. YAML = compromis lisibilité humaine + structure machine.

**Bloc `meta.judge_model` + `tolerance_default` à la racine** : AgBOM pinning au niveau du fichier de golden. Si demain on change le judge_model (`haiku-4.5` → `opus-4`), le bump est tracé dans git et tout le golden est ré-évalué. Pinner le modèle dans le golden lui-même (pas seulement dans le code Python) = le golden documente sa propre calibration cible — réplicable même 6 mois plus tard.

**`cited_policy_excerpt` inline (pas un `cited_policy_id` seul)** : le juge ne doit pas charger `docs/cancellation_policy.md` en runtime (sinon couplage golden ↔ filesystem ↔ chunking ↔ version du doc). L'extrait est figé dans le golden → reproductibilité totale, même si on modifie les docs sources demain. Trade-off : duplication ; bénéfice : isolation hermétique du test.

**`|` literal block (vs `>` folded)** : `|` préserve les retours à la ligne. `>` les transforme en espaces. Pour un draft où la structure (paragraphes, listes à puces) compte pour `ton`, `clarté` et `concision`, `|` est obligatoire — sans lui, un draft de 3 paragraphes deviendrait un mur de texte au moment où le juge le lit.

**Citer le VRAI texte des `docs/`, pas paraphraser** : le juge compare `draft_reply` à `cited_policy_excerpt` pour scorer `exactitude`. Si on paraphrase le doc dans le golden, on teste contre une policy *imaginaire* — la calibration ne reflète pas le comportement réel en prod (où l'agent retrieva le doc réel via `retrieve_docs`). Coller-collé depuis `docs/cancellation_policy.md` = fidélité maximum. Le golden devient un échantillon honnête du pipeline complet.

---

### `src/sandbox/evaluation/judge.py`

**Séparation `evaluation/` vs `tools/`** : `evaluation/judge.py` contient la logique LLM pure (prompt SYSTEM, appel HTTP, parsing, cache) — pas de Pydantic, pas de `TOOL_METADATA`, pas de contrat MCP. `tools/evaluate_answer.py` est le wrapper MCP (validation Pydantic + JSON Schema + metadata). Même pattern que `retrieval/bm25.py` ↔ `tools/retrieve_docs.py` ou `classification/rules.py` ↔ `tools/classify_ticket.py`. Logique pure réutilisable + frontière MCP propre.

**Cache JSON keyé sur `(MODEL, PROMPT_VERSION, payload)`** : un appel OpenRouter coûte ~50ms et $0.0002 ; sans cache, 6 cas de golden × 10 itérations de dev = 60 appels payés. Le hash sur le triplet garantit que (a) changer de modèle invalide le cache, (b) bumper le prompt invalide le cache, (c) même payload re-soumis = read instantané. Fichier JSON (pas SQLite) parce qu'à 6 cas × 1 modèle × 2 versions = ~12 entrées max — la simplicité gagne. `data/judge_cache.json` est dans `.gitignore` (artefact local).

**`temperature: 0` (pas `0.7` ni default)** : détermine la **reproductibilité** du juge. À `temperature=0.7`, deux runs du même cas peuvent donner `{clarté: 5}` puis `{clarté: 4}` → calibration impossible. À `0`, le LLM choisit toujours le token le plus probable → réponses quasi-identiques (variance résiduelle absorbée par `±1`). Le cache devient aussi pleinement efficace (même payload → même output → un seul appel facturé jamais re-déclenché).

**Bloc `CONTEXTE OPÉRATIONNEL` en tête du prompt SYSTEM (HITL framing)** : sans ce bloc, le juge traite le draft comme une action **autonome** envoyée au client → il pénalise tout engagement ("je procède à l'annulation") en confondant texte et exécution. Avec le bloc, le juge comprend que le draft est **proposé** à un humain qui valide → il juge la qualité du texte sans le confondre avec une décision exécutoire. C'est le pattern HITL du projet enseigné au LLM-juge lui-même.

**Instruction "Fais CONFIANCE aux classifications temporelles dans le draft"** : ajoutée en v2 du prompt après que le juge eut sur-pénalisé `cancellation-48h-clean-pass` (il doutait du "plus de 48 heures" alors que c'était notre prémisse de test). Décision : le juge n'est pas un classificateur temporel — il évalue la qualité du texte une fois la classification faite par d'autres tools (`classify_ticket` en amont). Sans cette ligne, le juge re-fait le travail d'un autre étage.

**`reasoning` AVANT les scores dans le JSON de sortie** : CoT lite. Le LLM remplit `reasoning` en premier → il **doit** justifier avant de scorer → le score reflète la justification, pas un guess gut-feeling. Si on mettait `reasoning` après, le LLM scorerait d'abord puis rationaliserait. Trade-off : génération un peu plus longue (~150 tokens) ; bénéfice : scores 2-3× plus stables entre runs et debuggables par lecture du `reasoning`.

**`_extract_json` tolérant (strip code fences + fallback first-`{` last-`}`)** : Claude wrappe parfois sa réponse JSON dans ` ```json ... ``` ` malgré l'instruction explicite contraire — `json.loads()` brut casse alors avec `Expecting value: line 1 column 1`. Logique : (1) strip les fences si présents, (2) si `json.loads` échoue quand même, fallback `text[first-{:last-}+1]` pour extraire le bloc JSON même au milieu de prose. Pattern défensif réutilisable pour toute API LLM.

**`load_dotenv()` au module-level** : charge `.env` à l'import → la clé `OPENROUTER_API_KEY` est dispo dès le premier appel sans qu'un caller doive penser à `dotenv` explicite. Trade-off : couplage à `python-dotenv` et import-time side-effect — accepté ici parce qu'on est dans un sandbox local, pas une lib distribuable. En prod : passage par config injecté.

---

### `src/sandbox/tools/evaluate_answer.py`

**Délégation pure à `judge.judge_answer`** : le tool ne contient **aucune** logique de prompt, de cache ou de parsing — juste validation Pydantic + 1 appel à `judge_answer()` + repackaging dans `EvaluateAnswerOutput`. Pattern identique à `retrieve_docs` ↔ `bm25` et `classify_ticket` ↔ `rules`. Si Phase 5 on remplace OpenRouter par Ollama local, **seul `judge.py` change**, le contrat MCP reste stable et les callers ne voient rien bouger.

**`risk_level="read"`** : aucune écriture DB, aucun envoi externe, idempotent (cache → 2e appel = read pur). Le seul side-effect est l'appel HTTP payant à OpenRouter, borné par le cache. Le Policy Server ne demandera pas de Vibe Diff pour `evaluate_answer`. Trade-off : si quelqu'un appelle 10 000 fois avec des payloads différents, la facture peut grimper — borner via budget côté Policy Server Phase 4.

**Stamping `judge_model` + `prompt_version` dans l'output (Vibe Trajectory)** : chaque score loggué dans la trajectory **emporte** le contexte de sa génération (quel modèle, quel prompt). Si un jour on découvre qu'un cas a été mis-scoré, on peut filtrer la trajectory par `(judge_model, prompt_version)` pour identifier la cohorte impactée et re-évaluer **uniquement** elle. Sans ce stamping, "le juge a donné 5" est une donnée orpheline — impossible de la rattacher à une version du système.

**`ge=0, le=5` Pydantic sur chaque dimension de l'output** : defense in depth. Le prompt dit "scores 0-5", `temperature=0` rend ça stable, `_extract_json` parse robustement — et **quand même** Pydantic borne à `[0, 5]`. Si le LLM hallucine `clarté: 7` un jour (changement de version provider, prompt mal compris), `ValidationError` tombe à la frontière du tool, pas dans la trajectory en aval. Trois couches de défense, parce que la quatrième (caller buggé) ne doit pas voir un score invalide.

**`Category = Literal[...]` réutilisé depuis `classification.rules`** : single source of truth. Si on ajoute une catégorie en Phase 5 (`refund` par ex), elle est ajoutée dans `rules.py` une fois, et `evaluate_answer` la valide automatiquement via l'import. Pas de drift entre les tools. Même pattern qu'avec `draft_reply.py`. La définition vit là où elle est calculée (rules), pas dupliquée partout.

---

### `tests/test_evaluate_answer.py`

**`@pytest.mark.parametrize(..., ids=[case["id"] ...])`** : chaque cas du golden devient un test pytest indépendant avec son ID lisible (`test_calibration[cancellation-48h-clean-pass]`). Si un cas casse, le rapport pytest pointe **directement** vers le case ID — pas besoin de chercher "le 3e cas du fichier". Le nom du test **EST** le diagnostic immédiat.

**`@pytest.mark.skipif("OPENROUTER_API_KEY" not in os.environ)` sur les tests de calibration** : les tests qui appellent le vrai juge ne tournent qu'en local (où la clé est dans `.env`). En CI sans clé, ils sont skipped (pas failed) → CI reste verte sans dépendance à un secret. Trade-off : la calibration n'est **pas** validée en CI automatiquement — accepté parce que c'est un sandbox d'apprentissage, pas une prod. En prod : monter un secret CI dédié.

**Collecter TOUS les deltas avant le `assert` (pas un `assert` par dim)** : un `assert score == expected` par dimension échouerait au premier delta → on ne verrait jamais les 6 autres. Pattern : accumuler `failures = [...]` puis `assert not failures, "\n".join(failures)`. Le rapport pytest montre **toutes** les dérives en un seul run → calibration en une itération au lieu de 7 cycles `run → fix → run`.

**Inclure le `reasoning` du juge dans le message d'erreur** : quand un cas échoue, le message contient `clarté: expected 5, got 3 — reasoning: "Le draft mélange deux structures..."`. Le **diagnostic du juge** est dans l'erreur de test → on lit pourquoi sans relancer en debug. C'est exactement ce qui a permis de découvrir les 3 bugs internes du golden (cas 1, 2, 6) sans effort d'investigation manuelle — le juge a écrit le diff lui-même.

**Pas de mocking du juge dans les tests de calibration** : mocker `judge_answer` reviendrait à tester "le mock renvoie ce qu'on lui dit" → tautologie. La calibration **doit** taper le vrai LLM, sinon on ne mesure rien. Coût : ~6 secondes pour 6 cas au premier run (cachés ensuite, donc ~0s). Bénéfice : calibration réelle, pas simulée. Les tests de contrat (Pydantic / metadata), eux, ne taillent pas le LLM — découpage strict.

**Tests "non calibration" (`test_pydantic_rejects_*`, `test_tool_metadata_shape`, `test_evaluate_answer_includes_audit_metadata`)** : les 4 tests qui valident le **contrat** du tool tournent **toujours** (pas de `skipif`), même sans clé API. Découpage : 6 tests de calibration (LLM) + 4 tests de contrat (Pydantic + metadata + stamping audit) = couverture complète sans dépendance forcée sur le secret. Pattern : isoler la couche LLM-dépendante de la couche contrat — les deux ont des cycles de vie différents.

---

## Phase 3 — *(à compléter)*
