# Socratic Project Auditor & Learning Examiner (`v1.3`)

**Fail-Closed Socratic Code & Document Defense Runtime with JSON Schema Draft 2020-12 Validation, Two-Stage Pedagogical Leakage Gate, and Immutable SQLite State Tracking**

[![Python 3.11+](https://img.shields.io/badge/Python-3.11%2B-blue.svg)](https://www.python.org/)
[![JSON Schema](https://img.shields.io/badge/JSON%20Schema-Draft%202020--12-007ec6.svg)](https://json-schema.org/draft/2020-12/schema)
[![Tests](https://img.shields.io/badge/Acceptance%20Tests-71%2F71%20Passing-brightgreen.svg)](#dogrulama-ve-test-paketi--verification--test-suite)

---

## 🇹🇷 Türkçe Özeti (Turkish Overview)

### Problem ve Amaç
Yapay zekâ destekli yazılım geliştirme süreçlerinde en kritik risklerden biri, geliştiricinin ürettiği veya sunduğu kodu, mimari tasarım kararlarını ve başvuru/fikir belgelerini nedensel mekanizmalarıyla savunamamasıdır. Sıradan dil modeli sohbetleri ise soru sorarken cevabı ağzından kaçırır, doğrudan çözüm kodu üretir veya belirsiz/akıcı yanıtları doğru kabul eder.

**Socratic Project Auditor (`proje-denetleyici-ve-ogrenim-sorgulayicisi`)**, hem **kod savunmasını (`v1.2`)** hem de **proje/belge savunmasını (`v1.3`)** aynı ajan kimliği altında, **çözüm üretmeden** ve **tamamen deterministik doğrulama kapılarından geçirerek** yürüten sohbetsiz (headless) bir çalışma zamanı (runtime) motorudur.

### Temel Yetenekler ve Mimari Güvenceler
1. **Çift Hatlı Sözleşme Mimarisi (Kod + Belge Savunması):**
   - **Kod Savunması (`PREPARE_EXAM` / `ANALYZE_RESPONSE`):** [`CONTRACT.md`](🛠️%20600-Arsenal/Ajanlar/proje-denetleyici-ve-ogrenim-sorgulayicisi/CONTRACT.md) uyarınca kod kesitleri (`start_line..end_line` LF satır bütünlüğü doğrulamalı) ve üst tasarım inceleme bulguları üzerinden kavramsal amaç, uç durum izleme ve mimari ödünleşme soruları üretir.
   - **Proje ve Belge Savunması (`PREPARE_PROJECT_DEFENSE` / `ANALYZE_PROJECT_DEFENSE`):** [`PROJECT_DEFENSE_CONTRACT.md`](🛠️%20600-Arsenal/Ajanlar/proje-denetleyici-ve-ogrenim-sorgulayicisi/PROJECT_DEFENSE_CONTRACT.md) uyarınca kodsuz fikir/başvuru belgelerini (`IDEA_PROPOSAL`), mimari şartnameleri (`ARCHITECTURE_SPEC`) ve `README`/tasarım belgelerini bölüm (`section_id`) ve pasaj (`passage_id`) bazında inceler. Belge ve kod savunmaları aynı projeye (`project_id`) bağlı **ayrı oturumlarda** yürütülür.
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
- **Dual-Contract Architecture:** Separate, strictly validated JSON Schema Draft 2020-12 contracts for line-bound code artifacts ([`CONTRACT.md`](🛠️%20600-Arsenal/Ajanlar/proje-denetleyici-ve-ogrenim-sorgulayicisi/CONTRACT.md)) and section/passage-bound project documents ([`PROJECT_DEFENSE_CONTRACT.md`](🛠️%20600-Arsenal/Ajanlar/proje-denetleyici-ve-ogrenim-sorgulayicisi/PROJECT_DEFENSE_CONTRACT.md)).
- **Long-Document Batching & Scope Matrix:** Tracks every document section across `PROBLEM`, `METHOD`, `DECISIONS_AND_TRADEOFFS`, `ASSUMPTIONS`, `BOUNDARIES_AND_RISKS`, and `SUCCESS_METRICS` as `INSPECTED`, `OPEN`, `ADDRESSED_WITH_TEACHING`, or `OUT_OF_SCOPE`. Uninspected batch sections and unreadable visual sections remain explicitly visible.
- **Fine-Grained Response Classification:** Distinguishes concise accurate explanations (`DIRECT_CRITERION_MATCH`) and valid alternative engineering designs (`ALTERNATIVE_VALID_EXPLANATION`) from superficial answers (`FLUENT_SUPERFICIAL_OR_EMPTY`), undocumented claims (`NOT_IN_DOCUMENT`), technical errors (`TECHNICALLY_INCORRECT`), and claims awaiting primary-source verification (`PENDING_EXTERNAL_VERIFICATION` with sanitized public search topics that never leak private project text).
- **Controlled Teaching Transition:** When the user declares *"I don't know"*, the runtime closes the active question/response defense record before delivering conceptual explanation and high-level approaches, permanently recording assistance on the affected dimension while preserving prior unassisted dimensions.

---

## Kurulum ve Hızlı Başlangıç / Installation & Quick Start

### Gereksinimler / Prerequisites
- **Python 3.11+**
- **PowerShell 7+ (`pwsh`)** veya Windows PowerShell
- *(Canlı model üretimi için)* Yerel `codex` CLI veya `ProjectAuditorRuntime(..., backend=...)` arayüzüne bağlanan özel model adaptörü. *(71 kabul testinin tamamı sentetik/izole çalışır, model kotası harcamaz).*

### Tek Komutla Kurulum / One-Command Setup
```powershell
git clone https://github.com/yalcin-ciftci/socratic-project-auditor.git
cd socratic-project-auditor
.\Setup-Agent.ps1
```

`Setup-Agent.ps1` betiği:
1. `.codex/.venv-project-auditor` altında izole Python sanal ortamını kurar,
2. `requirements.txt` içindeki zorunlu şema/takvim doğrulayıcılarını (`jsonschema`, `rfc3339-validator`) yükler,
3. **71/71** birim ve entegrasyon testini çalıştırarak kurulumu doğrular.

---

## CLI Kullanım Örnekleri / CLI Usage Examples

### 1. Belge Savunması Oturumu Başlatma ve İlk Soruyu Teslim Etme
```powershell
# 1) Belge savunması oturumunu SQLite üzerinde başlat
.\.codex\Invoke-ProjectAuditor.ps1 -Action init-doc-session `
  -SessionId "DSESS-20261017-01" `
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
  -SessionId "DSESS-20261017-01" `
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
.\.codex\Invoke-ProjectAuditor.ps1 -Action pause-doc-session -SessionId "DSESS-20261017-01" -AttemptId "DTURN-20261017-05"
.\.codex\Invoke-ProjectAuditor.ps1 -Action resume-doc-session -SessionId "DSESS-20261017-01" -AttemptId "DTURN-20261017-06"
.\.codex\Invoke-ProjectAuditor.ps1 -Action update-doc-version -SessionId "DSESS-20261017-01" `
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
- [`test_project_auditor_doc_defense.py`](.codex/tests/test_project_auditor_doc_defense.py): Kodsuz fikir/mimari/README belge savunması, 20+ kayıtlı uzun oturumlar, takip sorusu sınırları, `"Bilmiyorum"` -> öğretim geçişi, bölüm×boyut matrisi doğrulaması, belge sürümü değişikliği (`R1`) ve doğrulanmamış öğretim statüsü engellemesi (`R2`) regresyon testleri (**Toplam 71/71 test**).

---

## Doğrulanmış Metodolojik ve Teknik Sınırlar / Verified Boundaries

1. **Akademik Kaynak ve Çıkarım Ayrımı:**
   - [SocraticLM (NeurIPS 2024)](https://papers.nips.cc/paper_files/paper/2024/hash/9bae399d1f34b8650351c1bd3692aeae-Abstract-Conference.html) çalışmasındaki *Dean–Teacher–Student* yapısı çok ajanlı bir sentetik veri üretim hattıdır; bu çalışma katmanının doğrudan çalışma zamanı doğrulaması değildir.
   - [Prometheus (arXiv:2310.08491)](https://arxiv.org/abs/2310.08491) bulguları belirli model ve referans materyal koşullarına aittir. JSON Schema rubrik yapısı tek başına model değerlendirme doğruluğu garantisi sayılmaz; sistemin güvenilirliği kendi 71 kabul testi ve deterministik çalışma katmanı kurallarıyla ölçülür.
2. **Araçsız Çalışma (`tools=[]`) ve Veri Gizliliği Sınırı:**
   - Araçsız çalışma, yerel CLI yürütmesi, yerelde model çalıştırma ve veri gizliliği birbirinden ayrıdır. `CodexBackend` yerel süreçte dosya/ağ/kabuk araçlarını kapatsa da (`--sandbox read-only`), bulut tabanlı bir model kullanıldığında görev paketi ilgili model sağlayıcısına iletilir. Tam çevrimdışı gizlilik gerektiğinde `ProjectAuditorRuntime` içine yerel bir model adaptörü enjekte edilmelidir.
3. **Puan ve Kapı Onayı Üretmeme İlkesi:**
   - Bu motor genel başarı puanı, yüzdelik öğrenim skoru veya otomatik proje kapısı onayı üretmez; çıktıları yalnızca **yardımsız açıklanan (`unassisted_explained_dimensions`), yardımla açıklanan (`assisted_explained_dimensions`) ve açık kalan (`open_dimensions`)** boyutlar olarak kaydeder.
