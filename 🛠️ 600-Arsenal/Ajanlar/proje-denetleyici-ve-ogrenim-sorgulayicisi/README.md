---
title: "Ajan Ortamı: Proje Denetleyici ve Öğrenim Sorgulayıcısı"
created: 2026-10-16
modified: 2026-10-17
type: agent-environment
status: runtime-verified
tags: [agent, environment, socratic-examiner, project-auditor, pedagogy, document-defense, argon, headless]
---

# HarmanOS — Proje Denetleyici ve Öğrenim Sorgulayıcısı (`agent_project_auditor`)

> [!IMPORTANT]
> **Teslim ve Kabul Durumu (`v1.2` Kod Savunması: `runtime-verified` | Proje/Belge Savunması Uzantısı: `runtime-verified`):**
> - **Kod Savunması (`PREPARE_EXAM` / `ANALYZE_RESPONSE`):** [[Altıncı Uzman Ajan — v1.2 Tasarım Kabulü — 2026-10-16]] ve [[Altıncı Uzman Ajan — Runtime Kabulü — 2026-10-16]] ile kabul edilmiş ve çalışma katmanı doğrulanmıştır (`runtime-verified`).
> - **Proje ve Belge Savunması Uzantısı (`PREPARE_PROJECT_DEFENSE` / `ANALYZE_PROJECT_DEFENSE`):** Aynı altıncı uzman ajan kimliği korunarak fikir/başvuru belgeleri ve mimari/README belgeleri üzerinde proje hâkimiyeti sorgulaması için [[PROJECT_DEFENSE_CONTRACT|PROJECT_DEFENSE_CONTRACT.md]], `PROMPT.md` Bölüm 9 ve çalışma katmanı (`validation.py`, `store.py`, `delivery.py`, `runner.py`, `Invoke-ProjectAuditor.ps1`) güncellenmiştir. Bu uzantı **Codex Morks bağımsız incelemesinde kabul edilmiştir**: [[Altıncı Uzman Ajan — Belge Savunması Nihai Kabulü — 2026-10-17]].
> - Mevcut beş uzman ajanın sözleşmeleri ve `.codex/config.toml` değiştirilmemiştir.

Bu dizin, HarmanOS Baş Orkestratörü **Morks**'un sağladığı kapsam içi proje kanıtları, üst inceleme bulguları ve proje belgelerinden **Sokratik kod ve belge savunması soruları**, **kavramsal ipuçları**, **Morks'a özel değişmez değerlendirme ölçütleri (`criterion_id`)** ve **kanonik paketlere bağlı yanıt gözlemleri** üretmek için tasarlanan sohbetsiz (headless) alt yürütme motorunun şartname ortamıdır.

*(Tasarım ve Metodoloji Sınırı Notu: SocraticLM [NeurIPS 2024](https://papers.nips.cc/paper_files/paper/2024/hash/9bae399d1f34b8650351c1bd3692aeae-Abstract-Conference.html) çalışmasındaki Dean–Teacher–Student düzeni çok ajanlı bir **veri üretim hattıdır** ve çalışma zamanı mimarimizi doğrudan doğrulamaz. [Prometheus](https://arxiv.org/abs/2310.08491) sonuçları belirli model, referans materyal ve deney koşullarına aittir; rubrik şeması tek başına güvenilirlik garantisi sayılmaz ve ajanımızın doğruluğu kendi kabul örnekleriyle ölçülür. Ayrıca araçsız çalışma (`tools=[]`), yerel CLI yürütmesi, yerelde model çalıştırma ve veri gizliliği birbirinden ayrı kavramlardır: yerel `codex exec` süreci dosya/ağ aracı açmasa da istem yükü seçilen model sağlayıcısına iletilir; özel verinin sağlayıcıya aktarımı hakkında doğrulanmamış sıfır-veri-çıkışı güvencesi verilmez.)*

---

## 1. Ajan Kimliği ve Mimari Konumu

- **Ajan Kimliği:** `agent_project_auditor` (`proje-denetleyici-ve-ogrenim-sorgulayicisi`)
- **Tasarım Sürümü:** `v1.2` (Kod Savunması `runtime-verified`) + Belge Savunması Uzantısı (`v1` şeması, Morks kabul incelemesinde)
- **Çalışma Modeli:** Sohbetsiz Alt Yürütme Motoru (`tools=[]`, ağ/dosya/terminal/MCP/alt ajan erişimi kapalı; kod çitsiz ham JSON çıktısı)
- **Orkestrasyon Sözleşmeleri (Çift Hatlı Mimari):**
  1. **Kod Savunması Sözleşmesi (`CONTRACT.md`):** `harmanos.project_auditor.input.v1` -> `harmanos.project_auditor.output.v1` (`PREPARE_EXAM`, `ANALYZE_RESPONSE`). Mevcut `session_mode` alanı yalnızca kod savunmasına aittir; başka anlamda yeniden kullanılmaz.
  2. **Proje ve Belge Savunması Sözleşmesi (`PROJECT_DEFENSE_CONTRACT.md`):** `harmanos.project_auditor.doc_defense.input.v1` -> `harmanos.project_auditor.doc_defense.output.v1` (`PREPARE_PROJECT_DEFENSE`, `ANALYZE_PROJECT_DEFENSE`). Belge ve kod savunmaları aynı projeye (`project_id`) bağlı **ayrı oturumlarda** yürütülür; belge pasajları kod satırı gibi gösterilmez.
- **Kod Savunması Oturum Kipleri (`session_mode`):**
  1. `INDEPENDENT_EVIDENCE_COLLECTION`: Bağımsız yeterlik kanıtı / proje savunması hazırlığı. Daha önce rubrik veya teşhis açılmışsa (`rubric_or_diagnosis_disclosed: true`) pedagojik kilit (`PEDAGOGICAL_LOCK_TRIGGERED` / `RUBRIC_ALREADY_DISCLOSED_LOCK`) devreye girer.
  2. `GUIDED_PRACTICE`: Rehberli öğrenme ve tekrar kipi. Çıktı üretilebilir ancak değerlendirici köprüsünde bağımsız deneme adayı olamaz (`eligible_for_independent_attempt_submission: false`).
- **Desteklenen Kod Savunması İşlemleri (`operation`):**
  1. `PREPARE_EXAM` *(v1 ana işlemi)*: Kapsam içi kod kanıtları ve üst inceleme bulgularından değişmez kimlikli (`question_id`, `criterion_id`, `hint_id`) savunma paketi üretir. `allowed_assistance_level == "SILENT_OBSERVATION_ONLY"` ise soru üretimi ve kullanıcı teslimi hem şema hem `POST-03`/`DELIV-01` düzeyinde çift yönlü olarak kapatılır (`SILENT_OBSERVATION_COMPLETED`).
  2. `ANALYZE_RESPONSE` *(Kanonik sınav paketine bağlı destekleyici işlem)*: kullanıcı'in verdiği yanıtı yalnızca Morks'un yerel kanonik sınav deposundan (`local_exam_store[exam_id]`) kurulan ve SHA-256 özeti (`exam_package_sha256`) gövdeden yeniden hesaplanarak doğrulanan (`PRE-06`) `prior_exam_package` içindeki teslim edilmiş sorulara (`delivered_to_learner: true`) ve değişmez `criterion_id` ölçütlerine (`MET`, `NOT_MET`, `INSUFFICIENT_EVIDENCE`) göre gözlemler. `ANALYZE_RESPONSE` işleminde `SILENT_OBSERVATION_ONLY` izni şema düzeyinde yasaktır.
-- **Desteklenen Proje ve Belge Savunması İşlemleri (`operation`):**
  1. `PREPARE_PROJECT_DEFENSE`: Fikir/başvuru belgeleri (`IDEA_PROPOSAL`) ile mimari/README belgelerini (`ARCHITECTURE_SPEC`, `README_OVERVIEW`, `DESIGN_DECISION_RECORD`, `MIXED_PROJECT_DOC`) bölüm bölüm (`batch_index` / `total_batches`) inceler. Ana soru sayısı sabit değildir; incelenmeyen bölümler (`uninspected_section_ids`) ve okunamayan görseller (`waiting_visual_section_ids`) açıkça görünür tutulur. Her bölüm için ilgili boyutlar (`PROBLEM`, `METHOD`, `DECISIONS_AND_TRADEOFFS`, `ASSUMPTIONS`, `BOUNDARIES_AND_RISKS`, `SUCCESS_METRICS`) kapsam listesine bağlanır.
  2. `ANALYZE_PROJECT_DEFENSE`: Teslim edilmiş ana soru (`DQ-...`) veya nötr takip sorusu (`FQ-DQ-...-01`) için verilen ve SQLite'ta kayıtlı olan yanıtı yerel kanonik belge savunması paketine (`prior_defense_batch_package`, `batch_package_sha256` doğrulamalı) göre değerlendirir. Alternatif geçerli açıklamayı (`ALTERNATIVE_VALID_EXPLANATION`), kısa doğru yanıtı (`DIRECT_CRITERION_MATCH`), akıcı boş yanıtı (`FLUENT_SUPERFICIAL_OR_EMPTY`), belgede olmayanı (`NOT_IN_DOCUMENT`), teknik yanlışı (`TECHNICALLY_INCORRECT`), tasarım kararını gerekçesiz değiştiren yanıtı (`DESIGN_CHANGED_WITHOUT_RATIONALE`), dış birincil kaynak kontrolü gerektiren belirsiz iddiayı (`PENDING_EXTERNAL_VERIFICATION` — özel proje metni içermeyen `sanitized_public_search_topic` ile) ve sonuçsuz dış doğrulamayı (`UNVERIFIED_EXTERNAL_CLAIM`) birbirinden ayırır. Sonuçları yalnızca **yardımsız açıklanan (`unassisted_explained_dimensions`), yardımla açıklanan (`assisted_explained_dimensions`) ve açık kalan (`open_dimensions`) boyutlar** olarak kaydeder; genel başarı puanı, bağımsız uygulama yeterliği veya proje kapısı onayı üretmez.

---

## 2. Mevcut Beş Uzman Ajanla Yetki ve Sınır Ayrımı

Altıncı ajan; teknik hakemliğin, bağımsız öğrenme değerlendirmesinin veya hafıza/planlama denetiminin yerine geçmez:

| Bileşen | Tekil Yetki ve Sorumluluk Sınırı | Altıncı Ajanın Bu Sınıra Karşı Davranışı |
| :--- | :--- | :--- |
| **Veri Mühendisliği Tasarım İnceleyicisi** (`veri-muhendisligi-tasarim-inceleyicisi`) | Kendi MVP kapısı ve beceri sınırında teknik kusur, mekanizma, etki ve dar doğrulama fikri üretir. | Üst inceleyiciden gelen `upstream_review_refs` bulgularını soruya dönüştürür. Kendisi yeni bir teknik kusurdan şüphelenirse bunu doğrulanmış kusur veya proje genel risk hükmü olarak **yazamaz**; yalnızca `unverified_observations_requiring_review` altında `review_required: true` olarak işaretler. |
| **Bağımsız Öğrenme Değerlendiricisi** (`bagimsiz-ogrenme-degerlendiricisi`) | Kendi 5 alanı içinde gerçek denemeyi, yardım kaydını, açıklamayı ve `2/2` bağımsız uygulama şartını değerlendirir. | Bağımsızlık sınıfı (`result_class`), `2/2` sonucu veya sayısal aktif hatırlama puanı üretmez. Yalnızca Morks'un değerlendiriciye aktarabileceği `evaluator_bridge_manifest` hazırlar. Herhangi bir ipucu/rubrik kullanılmışsa veya günlük eksikse `eligible_for_independent_attempt_submission: false` şema düzeyinde zorunludur (`R6`). |
| **Hafıza Tutarlılığı Denetçisi** (`hafiza-tutarliligi-denetcisi`) | Sunulmuş hafıza pasajlarının karar ve tarih tutarlılığını inceler. | Kasa geçmişine erişmiş gibi davranamaz; yalnızca girdideki kaynak kimlikli `binding_constraints` verisini okur. |
| **Araştırma ve Karar Analisti** (`arastirma-ve-karar-analisti`) | Kaynaklı dış araştırma ve iddia doğrulaması yapar. | Dış kaynak, kütüphane dokümanı veya web araması yapamaz; kapalı dünya kanıtıyla sınırlıdır. |
| **Takvim ve İş Yükü Planlayıcısı** (`takvim-ve-is-yuku-planlayicisi`) | Kapasite ve tarih seçeneklerini inceler. | Sınav tarihi, tekrar takvimi, günlük soru kotası veya çalışma süresi atayamaz. |
| **Morks (Baş Orkestratör)** | Kaynakları ve kanonik `prior_exam_package` kaydını paketler, `PRE/POST/DELIV` doğrulayıcılarını çalıştırır ve deneme/soru bazlı kalıcı yardım günlüğünü (`ledger_revision`) yönetir. | Kullanıcıyla doğrudan konuşmaz; tüm çıktıyı Morks'un doğrulama ve teslim filtresine sunar. |

---

## 3. Mutlak Kırmızı Çizgiler ve Pedagojik Kilitler

### 3.1. Mutlak Çözüm Sızıntısı Yasağı ("KODU EFENDİM YAZAR!")
- **Tüm Alanlarda Sıfır Çözüm:** Soru metinlerinde, rubriklerde, ipuçlarında, hata mesajlarında ve örneklerde çözüm kodu, SQL/DDL/DML, git patch/diff, düzeltilmiş fonksiyon, çalıştırılabilir komut, uygulanabilir pseudocode veya **çözümü tamamen belirleyen sıralı sözel algoritma tarifi** üretmek kesinlikle yasaktır.
- **Bölünmüş İpucu Yasağı:** Çözümü birden fazla ipucuna veya farklı soruların alt maddelerine bölerek birleştirildiğinde tam cevabı verecek şekilde dağıtmak yasaktır.
- **Kod Yeniden Basım Yasağı:** Kullanıcının kodunu düzeltilmiş veya yeniden biçimlendirilmiş hâliyle çıktıda basmak yasaktır; yalnızca `artifact_id`, `snapshot_id` ve `start_line`..`end_line` referansı kullanılır.

### 3.2. Kapsam Kilidi (`C_PROGRAMMING` ve `42_PISCINE` Yasağı) ve Alan Matrisi
- `learning_domain == "C_PROGRAMMING"` veya `"42_PISCINE"`, `programming_language == "C"` ya da `project_context_type == "42_PISCINE"` / `"C_STANDALONE"` olan her girdi (Python veya Shell ile yazılmış bir 42 görevi dahil) değerlendirme yapılmaksızın `terminal_status: "OUT_OF_SCOPE"`, `error_code: "FORBIDDEN_DOMAIN_C_OR_42"` döndürür.
- Belirsiz `"OTHER"` dil veya bağlam etiketi şemadan kaldırılmıştır. Desteklenen 7 alan (`SQL_DATA_ENG`, `PYTHON_DATA_ENG`, `PYTHON_CORE_PE1`, `R_STATS`, `SPSS_STATS`, `CYBERSEC_UNI`, `HARMANOS_SYSTEM_ARCH`) ve bunların izin verilen dil/bağlam/değerlendirici eşlemeleri `CONTRACT.md` Bölüm 4.1'deki deterministik matrisle kilitlenmiştir.
- PE1 çalışmaları (`PYTHON_CORE_PE1`) veya HarmanOS altyapı betikleri (`HARMANOS_SYSTEM_ARCH`), `bagimsiz-ogrenme-degerlendiricisi` kapsamına sokulmak için sahte biçimde `PYTHON_DATA_ENG` olarak etiketlenemez (`compatible_with_learning_evaluator: false`, `mapped_evaluator_domain: null`, `eligible_for_independent_attempt_submission: false` şema düzeyinde zorunludur).
- E-Ticaret MVP (`project_context_type == "ECOMMERCE_MVP"`) girdilerinde `binding_constraints.binding_source_id: "DOC-ECOMMERCE-MVP-PLAN-V1"`, `current_gate_id` (`GATE-01..09`), `target_layer` ve 4 yasaklı araç (`dbt`, `Airflow`, `Kafka`, `Spark`) JSON Schema düzeyinde zorunludur (`null` veya boş dizi olamaz).

### 3.3. Kanonik Soru Seçimi, Bildirim Önceliği ve Deneme Bazlı Yardım Günlüğü (`R1`, `R2`, `R3`, `R6`)
- **Tüm Sorularda Tam Şema + İlk Soruda `Q-01-*` Kısıtı (`R1`):** `socratic_questions` dizisinde ortak `items` şeması tüm elemanları (`0..N`) tam olarak doğrular; ilk elemanın `Q-01-*` kimlik zorunluluğu `items` doğrulamasını atlamaması için ayrı bir `allOf` dalı içindeki `prefixItems` ile uygulanır.
- **Ters Yönlü Sessiz İnceleme Kilidi (`R2`):** Girdi veya çıktı `SILENT_OBSERVATION_ONLY` olduğunda `EXAM_PREPARED`, `PARTIAL_EXAM_PREPARED` veya `RESPONSE_ANALYZED` üretilmesi hem JSON Schema hem `POST-03`/`DELIV-01` tarafından engellenir; kullanıcıya hiçbir koşulda soru teslim edilmez.
- **Sabit Bildirim Şablonu Önceliği (`R3`):** `PARTIAL_EXAM_PREPARED` durumunda (ister `QUESTION_ONLY` ister ipucu izinli olsun) `TPL_NOTICE_PARTIAL_EVIDENCE` şablonu önceliklidir; `QUESTION_ONLY` kısıtı her iki durumda da `on_demand_hints: []` ile uygulanır. Tam kapsamlı (`EXAM_PREPARED`) çıktıda ise `QUESTION_ONLY` için `TPL_NOTICE_IN_SCOPE_QUESTION_ONLY`, ipucu izinli kip için `TPL_NOTICE_IN_SCOPE_ON_DEMAND_HINTS` zorunludur.
- **Bağımsız Deneme Adaylığı Kuralı (`R6`):** `eligible_for_independent_attempt_submission` alanı yalnızca `compatible_with_learning_evaluator == true`, `session_mode_evaluated == "INDEPENDENT_EVIDENCE_COLLECTION"`, `known_disclosed_assistance_class == "NONE_OBSERVED"` ve `effective_assistance_floor == "NONE_INDEPENDENT"` olduğunda `true` olabilir; herhangi bir ipucu/rubrik kullanılmışsa veya günlük eksikse şema düzeyinde `false` olmak zorundadır.

### 3.4. Soru Türleri ve İpucu Kademesi Ayrımı
- **Üç Soru Kategorisi (`question_type`):**
  1. `CONCEPTUAL_PURPOSE`: Seçilen yapının veya kuralın kavramsal amacı.
  2. `CODE_TRACE_AND_EDGE_CASE`: Belirli bir girdide kodun satır satır izlenmesi veya sınır durum davranışı.
  3. `ARCHITECTURAL_TRADEOFF`: Yalnızca mevcut kapı ve doğrulanmış beceri izin verdiğinde tasarım ödünleşmesi.
- Bu üç kategori zorluk/ipucu kademesi değildir ve her hedefte üçünün birden üretilmesi zorunlu değildir.

### 3.5. Satır Sayısı Doğrulaması, Takvim Zamanı, Bozuk Kod ve Kesilmiş Kanıt (`F4`, `R5`)
- **Satır Bütünlüğü (`PRE-04`):** `code_artifacts[i].content` LF (`\n`) normalize edildikten sonra gerçek satır sayısı `end_line - start_line + 1` değerine birebir eşit olmalıdır. Kesilmiş/parçalı (`TRUNCATED` / `FRAGMENT`) kesitlerde mevcut aralık `start_line..end_line` ile, dışarıda kalan satırlar ise zorunlu `omitted_line_ranges` dizisiyle beyan edilir.
- **Gerçek Takvim ve Saat Doğrulaması (`R5`):** `as_of`, (`prior_exam_package` nesne olduğunda zorunlu olan) `prior_exam_package.created_as_of` ve `as_of_evaluated` alanları hem `"format": "date-time"` ve artık yıl farkındalıklı ISO-8601 regex deseniyle (`02-31`, `25:61` ve artık yıl olmayan `2026-02-29` gibi geçersiz tarih/saatleri şemada reddeder; artık yıl `2024-02-29` tarihini kabul eder) hem de `PRE-03`/`POST-01` içinde `datetime.fromisoformat()` ile denetlenir.
- **Bozuk Kod (`SYNTAX_ERROR_OBSERVED`):** Girdinin JSON şeması geçerliyse sözdizimi hatalı kod `INVALID_INPUT_CONTRACT` veya `INSUFFICIENT_EVIDENCE` sayılmaz; statik olarak sorgulanabilir, ancak çalışma zamanı başarısı (`PASSED`) iddia edilemez.

### 3.6. Proje ve Belge Savunması Güvenceleri (`DOC-PRE-01..10`, `DOC-POST-01..12`, `DOC-DELIV-01..06`)
- **Ayrı Oturum ve Ayrı Tablolar:** Belge savunmaları kod savunmalarından ayrı oturumlarda (`defense_session_id`) ve SQLite içinde ayrı tablolarda (`doc_defense_sessions`, `doc_defense_scope_items`, `doc_defense_batches`, `doc_defense_questions`, `doc_defense_responses`, `doc_defense_events`) saklanır; kod geçmişindeki 20 kayıt sınırı belge oturumlarını kesmez.
- **Katkı ve Epistemik İddia Ayrımı:** Morks katkı, ekip rolü ve alınan yardım bilgilerini mevcut kayıtlardan hazırlar; eksik varsa yalnızca `missing_contribution_fields` sorulur (`missing_contribution_fields_to_ask` / `addresses_missing_contribution: true`). İddialar `IDEA` / `PLAN` / `IMPLEMENTATION` / `MEASURED_RESULT` olarak ayrılır; yalnızca kullanıcı beyanına (`USER_DECLARATION`) dayanan veya kanıt referansı (`observed_evidence_refs`) boş olan `MEASURED_RESULT` iddiası `EPISTEMIC_CLAIM_CONTRADICTION` (`DOC-PRE-05`) ile reddedilir.
- **Tek Soru ve Tek Nötr Takip:** Her seferinde tek soru teslim edilir. Belirsiz yanıta (`VAGUE_OR_INCOMPLETE_NEEDS_FOLLOWUP`) veya açıklanmamış tasarım değişikliği gerekçesine (`DESIGN_CHANGED_WITHOUT_RATIONALE`) soru başına en fazla bir nötr takip sorusu (`FQ-DQ-...-01`) sorulur; ilk yanıt ezilmez ve açık takip sorusu yanıtlanmadan sonraki ana soruya geçilemez.
- **“Bilmiyorum” (`is_idk_declaration: true`) ve Öğretim Geçişi:** Önce mevcut soru ve yanıtın savunma kaydı kapatılır (`defense_record_closed: true`), ardından açık öğretim geçişi (`IDK_DECLARED_READY_FOR_TEACHING` / `teaching_transition_packet`) yapılır. Öğretim Morks'un ayrı teslim yolundan (`doc-teach`) yürütülür; özel rubrik veya hazır proje kodu gösterilmez. Açıklama gösterilmeden önce yardım olayı (`TEACHING_EXPLANATION_SHOWN`) SQLite'a yazılır; aynı/etkilenen boyuttaki sonraki açıklamalar yardımlı (`ASSISTED`) sayılırken önceden verilmiş yardımsız (`UNASSISTED`) boyutlar korunur.
- **Hatalı Soru İptali ve Belge Sürümü Değişikliği:** Hatalı soru `void-doc-question` ile kullanıcı aleyhine sayılmadan iptal edilir; belge sürümü değişikliği (`update-doc-version`) geçmiş kayıtları silmez veya ezmez, değişen bölümleri ise önceki yardım geçmişini koruyarak yeniden `OPEN` durumuna alır.

---

## 4. Ortam Dosyaları
- [[CONTRACT|CONTRACT.md]]: Kod savunması için makinece doğrulanabilir JSON Schema (Draft 2020-12), durum×işlem×payload ve bildirim öncelik matrisleri, kanonik `prior_exam_package` (`created_as_of` dahil 4 zorunlu anahtar) SHA-256 doğrulaması, `PRE/POST/DELIV` çalışma katmanı kuralları ve 14 doğrulanmış JSON örnek/fixture.
- [[PROJECT_DEFENSE_CONTRACT|PROJECT_DEFENSE_CONTRACT.md]]: Proje ve belge savunması (`PREPARE_PROJECT_DEFENSE` ve `ANALYZE_PROJECT_DEFENSE`) için JSON Schema (Draft 2020-12), `DOC-PRE-01..10` / `DOC-POST-01..12` / `DOC-DELIV-01..06` kuralları, metodoloji sınırları ve 4 doğrulanmış kanonik JSON fixture.
- [[PROMPT|PROMPT.md]]: Sohbetsiz alt yürütme motorunun sistem talimatı (Bölüm 1–8 Kod Savunması, Bölüm 9 Proje ve Belge Savunması), kod çitsiz ham JSON kuralı ve güvenilmeyen veri ayraçları.
- [[RUNTIME|RUNTIME.md]]: Morks üzerinden kod ve belge savunması orkestrasyon akışı, CLI/launcher eylemleri ve yerel çalışma katmanı kuralları.
- [[Altıncı Uzman Ajan — v1.2 Tasarım Kabulü — 2026-10-16]] ve [[Altıncı Uzman Ajan — Runtime Kabulü — 2026-10-16]]: Kod savunması tasarım ve çalışma katmanı kabul raporları.

