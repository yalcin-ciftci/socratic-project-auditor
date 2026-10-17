# Socratic Project Auditor & Learning Examiner (`v1.3`)

> Örnek proje belgeleri, kimlikleri ve öğrenci yanıtları kurgusal test verileridir. Example project documents, identifiers, and learner responses are fictional test fixtures.

**Fail-Closed Socratic Code & Document Defense Runtime with JSON Schema Draft 2020-12 Validation, Two-Stage Pedagogical Leakage Gate, and Immutable SQLite State Tracking**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![JSON Schema](https://img.shields.io/badge/JSON%20Schema-Draft%202020--12-007ec6.svg)](https://json-schema.org/draft/2020-12/schema)
[![Tests](https://img.shields.io/badge/Acceptance%20Tests-86%2F86%20Passing-brightgreen.svg)](#dogrulama-ve-test-paketi--verification--test-suite)

---

## Hızlı kullanım / Quick start

Python 3.11+ ile klonlanan repo kökünde tek kurulum komutu:

```sh
python -m pip install .
```

Klonlamadan kurulum: `pipx install git+https://github.com/yalcin-ciftci/socratic-project-auditor.git`.
Windows'ta izole kurulum ve bütün testler için `./Setup-Agent.ps1` kullanılabilir.
Ollama sunucusunu başlatın ve kullanacağınız modeli bir kez indirin
(örnek: `ollama pull qwen2.5:7b`). Sonra:

```sh
auditor --file my_script.py --provider ollama --model qwen2.5:7b
auditor --doc README.md --provider ollama --model qwen2.5:7b
```

`auditor --file my_script.py` varsayılan olarak yerel Ollama / `qwen2.5:7b` kullanır.
Model adı bir örnektir; donanım ve model kapasitesi yanıt kalitesini etkiler.
Araç model indirmez, servis başlatmaz ve başka sağlayıcıya otomatik geçmez.

Terminalde sırayla yanıt verin. `/hint` ipucu ister; `/idk` veya `bilmiyorum` mevcut
savunma kaydını kapatıp kavramsal öğretime geçer. Ana soru başına en fazla bir nötr
takip sorusu sorulur. `/quit` oturumu duraklatır, kayıtlar korunur. Yeni `auditor`
çağrısı yeni oturum açar; kayıtların düşük seviyeli devam araçları
`python -m project_auditor_runtime` arayüzündedir.

### Sağlayıcılar / Providers

API anahtarını ortam değişkenine tanımlayın; komut satırına veya repoya yazmayın.
HTTP adaptörü Python standart kütüphanesini kullanır, SDK/Codex kurulumu gerekmez.

| `--provider` | Ayar | `--model` |
| --- | --- | --- |
| `ollama` (varsayılan) | Anahtarsız; `OLLAMA_HOST`, varsayılan `http://localhost:11434` | İndirdiğiniz model etiketi |
| `gemini` | `GEMINI_API_KEY` | Gemini API model kimliği |
| `openai` | `OPENAI_API_KEY` | Structured Outputs destekleyen model kimliği |
| `openrouter` | `OPENROUTER_API_KEY` | Structured Outputs destekleyen sağlayıcı/model kimliği |
| `codex` | Kurulu ve oturum açılmış Codex CLI | Varsayılan `gpt-6.1-sol` |

```sh
auditor --doc README.md --provider gemini --model YOUR_GEMINI_MODEL_ID
auditor --file my_script.py --provider openai --model YOUR_OPENAI_MODEL_ID
auditor --doc README.md --provider openrouter --model YOUR_PROVIDER/MODEL_ID
auditor --file my_script.py --provider codex --model gpt-6.1-sol
```

API modelleri için `--model` zorunludur. API kullanımı sağlayıcının ücret/kota
koşullarına tabidir. Uzak sağlayıcı kaynak metni ve yanıtları alır. Yerel Ollama
kullanımında Codex/Sol çağrılmaz. Çevrimdışı kullanım için modeli önceden indirin
ve `OLLAMA_HOST` değerini yerel sunucuda tutun; uzak bir host paketleri o sunucuya yollar.
Ollama isteklerinde `num_ctx=32768` kullanılır; büyük paketler/diller için
`OLLAMA_NUM_CTX` ile artırılabilir. Modelinizin bağlam sınırı ve yeterli RAM/VRAM gerekir.

### Otomatik paket / Automatic packets

- UTF-8 kaynak okunur, kod çalıştırılmaz. `.py`, `.sql`, `.r`, `.sps`, `.sh`, `.ps1`
  desteklenir; C/42 kapsam dışıdır. Belgeler Markdown/düz metindir. PDF/DOCX ayrıştırma
  veya resim/ek dosyaları otomatik açma yoktur; bağlı resimler incelenemeyen kapsamdır.
- Ham dosya SHA-256 özeti, LF-normalize metnin ayrı özeti, gerçek satır aralıkları,
  başlıklar, bölüm/pasaj kimlikleri otomatik üretilir. Markdown kod çitleri başlık
  sayılmaz. Kaynak en fazla 1 MiB / 64 bölüm; bölüm en fazla 80 satır / 6000 karakterdir.
  Dörder bölümlük gruplar işlenir. Aşırı uzun tek satır/kapsam açık hata verir, kırpılmaz.
- `--file` kodu **HYBRID_SPEC belge savunması** olarak paketler: kodun gerekçesi,
  takip, ipucu ve öğretim aynı kontrollü oturumda yürür. Satıra bağlı ayrı
  `PREPARE_EXAM` / `ANALYZE_RESPONSE` kod sözleşmesi düşük seviyeli API'de korunur;
  her iki çıktı şeması bütün backend'lerde desteklenir.
- Katkı, ekip rolü, önceki yardım ve yeterlik bilinmiyorsa uydurulmaz. Belge iddiaları
  başlangıçta plan sayılır; statik kod varlığı çalıştırma/ölçüm kanıtı değildir.
- SQLite, yanıtlar ve kaynak envanteri varsayılan `~/.socratic-project-auditor/`
  altında saklanır. Bu dizin özel rubrik ve kaynak metni de içerir; Git'e eklemeyin.
  Oturumun bitmesi bütün boyutlarda öğrenme/bağımsız yeterlik anlamına gelmez.

```sh
auditor --file my_script.py --dry-run
auditor --doc README.md --state-dir ./private-auditor-state --timeout 300
```

`--dry-run` paketi gösterir; modele bağlanmaz ve durum yazmaz.

### Structured Outputs

Çıktı sözleşmesi model isteğine bağlanır:
[Gemini `responseJsonSchema`](https://ai.google.dev/gemini-api/docs/structured-output),
[OpenAI `response_format`](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=chat),
[OpenRouter `response_format`](https://openrouter.ai/docs/guides/features/structured-outputs) ve
[Ollama `format`](https://docs.ollama.com/api/chat).
Sağlayıcılar Draft 2020-12'nin tamamını desteklemediğinden taşınabilir yapısal şema
(türler, alanlar, enumlar, iç içe nesneler) gönderilir. Koşullar, kimlikler, uzunluklar
ve bütün diğer kısıtlar **tam orijinal sözleşmeyle yerelde tekrar doğrulanır**.
JSON moduna geri dönüş/sınırsız deneme yoktur: `POST-01` / `DOC-POST-01` için
en fazla bir format onarımı korunur. Semantik ve teslim kontrolleri de seçilen
backend ile yapılır; soru başına birden fazla model çağrısı olabilir.
Hata, ret veya kesilmiş yanıt teslimi durdurur. Geçerli JSON pedagojik doğruluk
garantisi değildir; küçük modeller anlam/doğrulama kapılarını geçemeyebilir.

### Dizin yapısı / Layout

```text
src/project_auditor_runtime/  # CLI, packager, backends, validation, delivery, SQLite
specs/                       # contracts/prompts, bundled in installed wheels
.codex/tests/                # original acceptance + new product integration tests
.codex/                      # optional Codex profile and advanced wrapper
pyproject.toml               # package and auditor console command
```

Installed wheels include the contracts and work outside the checkout. No HarmanOS
vault is needed. The resolver retains an optional legacy integration fallback.

---

## 🇹🇷 Türkçe Özeti (Turkish Overview)

### Problem ve Amaç
Yapay zekâ destekli yazılım geliştirme süreçlerinde en kritik risklerden biri, geliştiricinin ürettiği veya sunduğu kodu, mimari tasarım kararlarını ve başvuru/fikir belgelerini nedensel mekanizmalarıyla savunamamasıdır. Sıradan dil modeli sohbetleri ise soru sorarken cevabı ağzından kaçırır, doğrudan çözüm kodu üretir veya belirsiz/akıcı yanıtları doğru kabul eder.

**Socratic Project Auditor (`proje-denetleyici-ve-ogrenim-sorgulayicisi`)**, hem **kod savunmasını (`v1.2`)** hem de **proje/belge savunmasını (`v1.3`)** aynı ajan kimliği altında, **çözüm üretmeden** ve **tamamen deterministik doğrulama kapılarından geçirerek** yürüten sohbetsiz (headless) bir çalışma zamanı (runtime) motorudur.

### Temel Yetenekler ve Mimari Güvenceler
1. **Çift Hatlı Sözleşme Mimarisi (Kod + Belge Savunması):**
   - **Kod Savunması (`PREPARE_EXAM` / `ANALYZE_RESPONSE`):** [`CONTRACT.md`](specs/CONTRACT.md) uyarınca kod kesitleri (`start_line..end_line` LF satır bütünlüğü doğrulamalı) ve üst tasarım inceleme bulguları üzerinden kavramsal amaç, uç durum izleme ve mimari ödünleşme soruları üretir.
   - **Proje ve Belge Savunması (`PREPARE_PROJECT_DEFENSE` / `ANALYZE_PROJECT_DEFENSE`):** [`PROJECT_DEFENSE_CONTRACT.md`](specs/PROJECT_DEFENSE_CONTRACT.md) uyarınca kodsuz fikir/başvuru belgelerini (`IDEA_PROPOSAL`), mimari şartnameleri (`ARCHITECTURE_SPEC`) ve `README`/tasarım belgelerini bölüm (`section_id`) ve pasaj (`passage_id`) bazında inceler. Belge ve kod savunmaları aynı projeye (`project_id`) bağlı **ayrı oturumlarda** yürütülür.
2. **Epistemik İddia ve Kanıt Ayrımı (`DOC-PRE-05`):**
   - İddialar `IDEA`, `PLAN`, `IMPLEMENTATION` ve `MEASURED_RESULT` olarak; kanıt dayanakları ise `USER_DECLARATION` ve `OBSERVED_EVIDENCE` olarak ayrılır. Yalnızca kullanıcı beyanına dayanan veya gözlenmiş kanıt referansı olmayan bir "ölçülmüş sonuç" iddiası çalışma katmanı tarafından reddedilir (`EPISTEMIC_CLAIM_CONTRADICTION`).
3. **Çok Katmanlı Fail-Closed Doğrulama (`PRE` -> `POST` -> `DELIV`):**
   - **Sıkı JSON Ayrıştırıcı (`strict_json`):** Yinelenen anahtarları (duplicate keys), `NaN`/`Infinity` değerlerini ve bozuk UTF-8 dizilerini reddeder.
   - **Preflight & Postflight (`validation.py`):** Girdi ve çıktıları JSON Schema Draft 2020-12, artık yıl duyarlı RFC3339 takvim zamanı ve kanonik SHA-256 paket özeti (`exam_package_sha256` / `batch_package_sha256`) ile doğrular.
   - **İki Aşamalı Teslim Kapısı (`delivery.py`):** Kullanıcıya tek bir soru, takip sorusu, ipucu veya öğretim paketi gösterilmeden önce hem leksikal/regex tabanlı çözüm sızıntısı taraması hem de ikincil semantik güvenlik denetimi çalışır. Özel rubrik (`criterion_text`) veya çözüm kodu sızıntısı tespit edilirse teslim kilitlenir (`PEDAGOGICAL_LOCK_TRIGGERED`).
4. **SQLite Değişmez Durum, Takip ve Öğretim Geçişi (`store.py`):**
   - Her seferinde **yalnız tek soru** teslim edilir.
   - Belirsiz yanıta (`VAGUE_OR_INCOMPLETE_NEEDS_FOLLOWUP`) veya gerekçesi açıklanmamış tasarım değişikliğine (`DESIGN_CHANGED_WITHOUT_RATIONALE`) ana soru başına **en fazla 1 nötr takip sorusu (`FQ-DQ-...-01`)** sorulur; ilk yanıt asla ezilmez.
   - **"Bilmiyorum" (`is_idk_declaration: true`) Durumunda Öğretim:** Önce mevcut soru ve yanıtın savunma kaydı kapatılır (`defense_record_closed: true`), ardından ayrı öğretim teslim yolu (`doc-teach`) üzerinden özel rubrik veya hazır proje kodu açılmadan kavram, gerekçe ve olası yaklaşımlar açıklanır. Açıklama gösterilmeden önce yardım kaydı SQLite'a işlenir; aynı boyuttaki sonraki açıklamalar **yardımla açıklanan (`assisted_explained_dimensions`)** sayılırken önceden verilmiş **yardımsız (`unassisted_explained_dimensions`)** yanıtlar korunur.
   - **Belge Sürümü Güncellemesi ve Hatalı Soru İptali:** Hatalı sorular kullanıcı aleyhine sayılmadan iptal edilir (`void-doc-question`). Belge güncellendiğinde (`update-doc-version`) eski sürümün bekleyen soruları üzerinden teslim/ipucu/yanıt mutasyonu engellenir (`STALE_BATCH_DOCUMENT_VERSION`) ve yalnız değişen bölümler önceki yardım geçmişi korunarak yeniden `OPEN` durumuna alınır.

---

## 🇬🇧 English Overview

### Problem & Purpose
In AI-assisted engineering workflows, developers often struggle to defend the causal mechanisms behind their code, architectural trade-offs, and project proposals. Standard conversational LLMs frequently leak answers inside their questions, generate direct code fixes, or accept fluent but superficial explanations.

**Socratic Project Auditor** is a headless, fail-closed Socratic defense runtime that conducts both **Code Defense (`v1.2`)** and **Project/Document Defense (`v1.3`)** without generating solutions, arbitrary numerical scores, or unverified approvals.

### Key Architectural Guarantees
- **Dual-Contract Architecture:** Separate, strictly validated JSON Schema Draft 2020-12 contracts for line-bound code artifacts ([`CONTRACT.md`](specs/CONTRACT.md)) and section/passage-bound project documents ([`PROJECT_DEFENSE_CONTRACT.md`](specs/PROJECT_DEFENSE_CONTRACT.md)).
- **Long-Document Batching & Scope Matrix:** Tracks every document section across `PROBLEM`, `METHOD`, `DECISIONS_AND_TRADEOFFS`, `ASSUMPTIONS`, `BOUNDARIES_AND_RISKS`, and `SUCCESS_METRICS` as `INSPECTED`, `OPEN`, `ADDRESSED_WITH_TEACHING`, or `OUT_OF_SCOPE`. Uninspected batch sections and unreadable visual sections remain explicitly visible.
- **Fine-Grained Response Classification:** Distinguishes concise accurate explanations (`DIRECT_CRITERION_MATCH`) and valid alternative engineering designs (`ALTERNATIVE_VALID_EXPLANATION`) from superficial answers (`FLUENT_SUPERFICIAL_OR_EMPTY`), undocumented claims (`NOT_IN_DOCUMENT`), technical errors (`TECHNICALLY_INCORRECT`), and claims awaiting primary-source verification (`PENDING_EXTERNAL_VERIFICATION` with sanitized public search topics that never leak private project text).
- **Controlled Teaching Transition:** When the user declares *"I don't know"*, the runtime closes the active question/response defense record before delivering conceptual explanation and high-level approaches, permanently recording assistance on the affected dimension while preserving prior unassisted dimensions.

---

## Kurulum ve Hızlı Başlangıç / Installation & Quick Start

### Gereksinimler / Prerequisites
- **Python 3.11+**
- PowerShell yalnız Windows kurulum betiği için isteğe bağlıdır; `pip install .` çapraz platformdur.
- Canlı üretim için Ollama veya Gemini/OpenAI/OpenRouter API erişimi; Codex CLI isteğe bağlıdır. Testler model kotası harcamaz.

### Tek Komutla Kurulum / One-Command Setup
```powershell
git clone https://github.com/yalcin-ciftci/socratic-project-auditor.git
cd socratic-project-auditor
.\Setup-Agent.ps1
```

`Setup-Agent.ps1` betiği:
1. `.codex/.venv-project-auditor` altında izole Python sanal ortamını kurar,
2. `auditor` komutunu, gömülü sözleşmeleri ve zorunlu doğrulayıcıları yükler,
3. Mevcut 71 kabul testi ve yeni ürün testlerini çalıştırarak kurulumu doğrular.

---

## Gelişmiş Runtime CLI / Advanced Runtime CLI

### 1. Belge Savunması Oturumu Başlatma ve İlk Soruyu Teslim Etme
```powershell
# 1) Belge savunması oturumunu SQLite üzerinde başlat
.\.codex\Invoke-ProjectAuditor.ps1 -Action init-doc-session `
  -SessionId "DDS-20261017-01" `
  -Request path\to\prepare_doc_request.json

# 2) PREPARE_PROJECT_DEFENSE çalıştır ve yalnızca ilk nötr soruyu teslim et (-Deliver)
.\.codex\Invoke-ProjectAuditor.ps1 -Action run `
  -ExamId "DBATCH-20261017-01" `
  -AttemptId "DTURN-20261017-01" `
  -Request path\to\prepare_doc_request.json `
  -Deliver
```

### 2. Yanıt Kaydetme, Takip Sorusu, Öğretim Geçişi ve Oturum Durumu
```powershell
# Kullanıcı yanıtını SQLite'a kaydet
.\.codex\Invoke-ProjectAuditor.ps1 -Action record-doc-response `
  -SessionId "DDS-20261017-01" `
  -ExamId "DBATCH-20261017-01" `
  -AttemptId "DTURN-20261017-02" `
  -Request path\to\response_payload.json

# Kayıtlı nötr takip sorusunu teslim et (ana soru başına en fazla 1 adet)
.\.codex\Invoke-ProjectAuditor.ps1 -Action doc-followup `
  -ExamId "DBATCH-20261017-01" `
  -AttemptId "DTURN-20261017-03" `
  -QuestionId "FQ-DQ-01-METHOD-01" `
  -Request path\to\analyze_output.json

# "Bilmiyorum" bildirimi sonrası savunma kaydını kapatıp kavramsal öğretim paketini teslim et
.\.codex\Invoke-ProjectAuditor.ps1 -Action doc-teach `
  -ExamId "DBATCH-20261017-01" `
  -AttemptId "DTURN-20261017-04" `
  -QuestionId "DQ-01-METHOD" `
  -ResponseId "DRESP-01" `
  -Request path\to\teach_request.json

# Oturumu duraklat / devam ettir / belge sürümünü güncelle
.\.codex\Invoke-ProjectAuditor.ps1 -Action pause-doc-session -SessionId "DDS-20261017-01" -AttemptId "DTURN-20261017-05"
.\.codex\Invoke-ProjectAuditor.ps1 -Action resume-doc-session -SessionId "DDS-20261017-01" -AttemptId "DTURN-20261017-06"
.\.codex\Invoke-ProjectAuditor.ps1 -Action update-doc-version -SessionId "DDS-20261017-01" `
  -DocumentVersion "v2.0" -DocumentSha256 ("b" * 64) -Request path\to\updated_sections.json
```

---

## Doğrulama ve Test Paketi / Verification & Test Suite

Testleri istediğiniz zaman doğrudan çalıştırabilirsiniz:
```powershell
.\.codex\.venv-project-auditor\Scripts\python.exe -X utf8 -m unittest discover -s .codex/tests -p "test_project_auditor_*.py" -v
```

- [`test_project_auditor_validation.py`](.codex/tests/test_project_auditor_validation.py): Sıkı JSON ayrıştırma, LF satır normalizasyonu, kanonik SHA-256 ve şema doğrulama testleri.
- [`test_project_auditor_integration.py`](.codex/tests/test_project_auditor_integration.py): Kod savunması (`PRE/POST/DELIV`), eşzamanlı SQLite revizyon kilidi (`OCC`), tek seferlik şema onarımı ve izole `CodexBackend` taşıma katmanı testleri.
- [`test_project_auditor_doc_defense.py`](.codex/tests/test_project_auditor_doc_defense.py): Kodsuz fikir/mimari/README belge savunması, 20+ kayıtlı uzun oturumlar, takip sorusu sınırları, `"Bilmiyorum"` -> öğretim geçişi, bölüm×boyut matrisi doğrulaması, belge sürümü değişikliği (`R1`) ve doğrulanmamış öğretim statüsü engellemesi (`R2`) regresyon testleri (Orijinal kabul paketi: 71 test; ürün testleri ayrıca eklenmiştir).

---

## Doğrulanmış Metodolojik ve Teknik Sınırlar / Verified Boundaries

1. **Akademik Kaynak ve Çıkarım Ayrımı:**
   - [SocraticLM (NeurIPS 2024)](https://papers.nips.cc/paper_files/paper/2024/hash/9bae399d1f34b8650351c1bd3692aeae-Abstract-Conference.html) çalışmasındaki *Dean–Teacher–Student* yapısı çok ajanlı bir sentetik veri üretim hattıdır; bu çalışma katmanının doğrudan çalışma zamanı doğrulaması değildir.
   - [Prometheus (arXiv:2310.08491)](https://arxiv.org/abs/2310.08491) bulguları belirli model ve referans materyal koşullarına aittir. JSON Schema rubrik yapısı tek başına model değerlendirme doğruluğu garantisi sayılmaz; sistemin güvenilirliği kabul testleri ve deterministik çalışma katmanı kurallarıyla ölçülür.
2. **Araçsız Çalışma (`tools=[]`) ve Veri Gizliliği Sınırı:**
   - Araçsız çalışma, yerel CLI yürütmesi, yerelde model çalıştırma ve veri gizliliği birbirinden ayrıdır. `CodexBackend` yerel süreçte dosya/ağ/kabuk araçlarını kapatsa da (`--sandbox read-only`), bulut tabanlı bir model kullanıldığında görev paketi ilgili model sağlayıcısına iletilir. Yerel Ollama adaptörü dahildir; `--provider ollama` ile kullanılır.
3. **Puan ve Kapı Onayı Üretmeme İlkesi:**
   - Bu motor genel başarı puanı, yüzdelik öğrenim skoru veya otomatik proje kapısı onayı üretmez; çıktıları yalnızca **yardımsız açıklanan (`unassisted_explained_dimensions`), yardımla açıklanan (`assisted_explained_dimensions`) ve açık kalan (`open_dimensions`)** boyutlar olarak kaydeder.
