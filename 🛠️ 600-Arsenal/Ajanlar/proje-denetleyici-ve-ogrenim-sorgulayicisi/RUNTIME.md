---
title: Altıncı Uzman Ajan — Çalışma Katmanı ve Kullanım
created: 2026-10-16
modified: 2026-10-17
type: runtime-guide
status: runtime-verified
tags: [agent, runtime, socratic, pedagogy, document-defense]
---

# Morks üzerinden kullanım

kullanıcı, “Bu projeyi savunma sorularıyla inceleyelim”, “Bu başvuru/mimari belgesini sorgula” veya “Yazdığım bu bölümü anlayıp anlamadığımı sorgula” dediğinde Morks bu motoru kullanır. Kullanıcı terminal komutu veya JSON hazırlamak zorunda değildir. Her seferinde tek kapsam ve doğrulanmış beceri zemini seçilir; C/42 kapsam dışıdır. Proje kodunu kullanıcı yazar.

Belge ve kod savunmaları aynı projeye (`project_id`) bağlı **ayrı oturumlarda** yürütülür:
- **Kod Savunması (`PREPARE_EXAM` / `ANALYZE_RESPONSE`):** Gerçek kod kesitini ve mevcut inceleme bulgularını paketler; ilk nötr soruyu gösterir. Rubrik ve açılmamış ipuçları özel kalır. İpucu ancak talep üzerine açılır ve gösterilmeden önce yardım kaydına yazılır. Yanıt gözlemi bağımsız öğrenme veya 2/2 kararı değildir; uygun alandaki gerçek kanıt mevcut değerlendiriciye aktarılır.
- **Proje ve Belge Savunması (`PREPARE_PROJECT_DEFENSE` / `ANALYZE_PROJECT_DEFENSE`):** Fikir/başvuru belgeleri ile mimari/README belgelerini bölüm bölüm inceler; incelenmeyen bölümler ve okunamayan görseller görünür tutulur. Katkı, ekip rolü ve alınan yardım bilgilerini Morks mevcut kayıtlardan hazırlar; yalnız eksikleri sorar. Sonuçlar **yardımsız açıklanan, yardımla açıklanan ve açık kalan boyutlar** olarak kaydedilir; genel başarı puanı, bağımsız uygulama yeterliği veya proje kapısı onayı üretilmez.

## Yetkili orkestratör akışı — Kod Savunması

1. `.codex/Invoke-ProjectAuditor.ps1 -Action init-ledger -LedgerId LEDGER-...` ile yerel yardım kaydını açıkça başlat. Modelden gelen geçmişle yerel kayıt oluşturma.
2. `CONTRACT.md` girdi şemasını esas al; `state` sonucundan alınan gerçek `disclosure_state` değerini kullan. Mevcut görevde aynı hedef/artefaktın geçmişini koru. Genel öğrenci yeterliği veya ilerleme uydurma.
3. `-Action run -Request <paket.json> -ExamId EXAM-YYYYMMDD-... -AttemptId ATT-YYYYMMDD-01 -Deliver` PRE, model, POST ve ilk teslim denetimlerini uygular. `-Deliver` yoksa yalnız özel paket hazırlanır; kullanıcıya soru gösterilmiş sayılmaz.
4. İpucu talebinde önce `state` ile güncel revizyonu al, ardından `hint` eyleminde sınav/soru/ipucu kimliğini kullan. Sonraki sorudan önce yanıt `record-response` ile kaydedilir; `next` eylemi önceki yanıtı ve sıralamayı doğrular.
5. Yanıt değerlendirmesinde `state -ExamId ...` ile yerel kanonik `prior_exam_package` görünümünü al. Bu görünüm yalnız gerçekten teslim edilmiş soruları içerir; henüz açılmamış soruları yanıt paketine ekleme. `ANALYZE_RESPONSE` güncel kanonik hash ve revizyonla çalışır.

## Yetkili orkestratör akışı — Proje ve Belge Savunması

1. `.codex/Invoke-ProjectAuditor.ps1 -Action init-doc-session -SessionId DDS-... -ProjectId PROJ-... -DocumentId DOC-... -DocumentVersion v1.0 -DocumentSha256 sha256:... -Request <belge_girdisi.json>` (veya kimlik alanlarını doğrudan `-Request <belge_girdisi.json>` içinden okuyarak) ile belge oturumunu (`defense_session_id`), tam bölüm envanterini (`full_section_inventory`) ve bölüm kapsam boyutlarını (`PROBLEM`, `METHOD`, `DECISIONS_AND_TRADEOFFS`, `ASSUMPTIONS`, `BOUNDARIES_AND_RISKS`, `SUCCESS_METRICS`) ayrı SQLite tablolarında başlat.
2. `PROJECT_DEFENSE_CONTRACT.md` girdi şemasını esas al (`PREPARE_PROJECT_DEFENSE`). Uzun belgeleri sıralı paketlere (`batch_index` / `total_batches`) ayır; `full_section_inventory` içindeki `in_current_batch` ve `has_unreadable_visuals` bayrakları ile çıktıdaki `inspected_section_ids_in_batch`, `uninspected_section_ids` ve `waiting_visual_section_ids` tam envanteri eksiksiz ve deterministik örtmelidir (`DOC-PRE-04`, `DOC-POST-02`, `DOC-POST-05`).
3. `.codex/Invoke-ProjectAuditor.ps1 -Action run -Request <belge_paketi.json> -ExamId DBATCH-YYYYMMDD-... -AttemptId DTURN-YYYYMMDD-01 -Deliver` ile `DOC-PRE-01..10`, model, `DOC-POST-01..12` ve ilk soru teslim denetimlerini (`DOC-DELIV-01..06`) uygula. Sorular ve özel ölçütleri teslimden önce SQLite'a kaydedilir; her seferinde yalnız tek soru gösterilir. Sonraki ana soru `-Action doc-next -Request <belge_paketi.json> -ExamId DBATCH-... -AttemptId DTURN-... -QuestionId DQ-...`, kavramsal ipucu ise `-Action doc-hint -Request <belge_paketi.json> -ExamId DBATCH-... -AttemptId DTURN-... -QuestionId DQ-... -HintId DH-...` ile teslim edilir.
4. Yanıt geldiğinde `.codex/Invoke-ProjectAuditor.ps1 -Action record-doc-response -SessionId DDS-... -ExamId DBATCH-... -AttemptId DTURN-... -QuestionId DQ-... -ResponseId DRESP-... -Request <yanit.json>` (`raw_response_text`, `is_idk_declaration`, `declared_design_change` alanlarını içeren JSON) ile yanıtı SQLite'a kaydet.
5. `ANALYZE_PROJECT_DEFENSE` çağrısından önce `.codex/Invoke-ProjectAuditor.ps1 -Action doc-state -SessionId DDS-... -ExamId DBATCH-...` ile yerel kanonik `prior_defense_batch_package` görünümünü (`batch_package_sha256` dahil), `session_state_snapshot` nesnesini ve tam oturum devam manifestosunu (`resume_manifest`, 20 kayıt sınırı olmadan) al. `ANALYZE_PROJECT_DEFENSE` girdisindeki `defense_responses` dizisi SQLite'ta kayıtlı yanıtlarla (`response_text`, `is_idk_declaration`, `declared_design_change`, belge sürümü/hash) birebir eşleşmek zorundadır (`DOC-PRE-06`).
   - Yanıt belirsizse (`VAGUE_OR_INCOMPLETE_NEEDS_FOLLOWUP`) veya tasarım değişikliği gerekçesi açıklanmamışsa (`DESIGN_CHANGED_WITHOUT_RATIONALE`), soru başına en fazla bir nötr takip sorusu (`FQ-DQ-...-01`) ayrı kimlikle kaydedilir; `-Deliver` anahtarı veya `-Action doc-followup -Request <belge_paketi.json> -ExamId DBATCH-... -AttemptId DTURN-... -QuestionId FQ-DQ-...-01` ile teslim edilir ve ilk yanıt ezilmez. Açık bir takip sorusu yanıtlanmadan (veya iptal/kapatma olmadan) `doc-next` ile sonraki ana soruya geçilemez.
   - Belge dışı teknik iddia birincil kaynak kontrolü gerektiriyorsa (`PENDING_EXTERNAL_VERIFICATION`), Morks özel proje metnini arama sorgusuna taşımadan yalnız `sanitized_public_search_topic` ile herkese açık birincil kaynakları kontrol eder; kontrol sonuçsuzsa `UNVERIFIED_EXTERNAL_CLAIM` olarak bırakılır (olumlu/olumsuz hüküm uydurulmaz).
   - kullanıcı **“Bilmiyorum”** (`is_idk_declaration: true`) dediğinde `ANALYZE_PROJECT_DEFENSE` (`IDK_DECLARED_READY_FOR_TEACHING`) mevcut soru ve yanıtın savunma kaydını kapatır (`defense_record_closed: true`); ardından `.codex/Invoke-ProjectAuditor.ps1 -Action doc-teach -ExamId DBATCH-... -AttemptId DTURN-... -QuestionId DQ-... -ResponseId DRESP-... -Request <ogretim_istegi.json>` (`payload` ve `teaching_transition_packet` içeren JSON) ile ayrı öğretim teslim yolundan kavram, gerekçe ve olası yaklaşımlar açıklanır. Açıklama gösterilmeden önce yardım kaydı (`TEACHING_EXPLANATION_SHOWN`) SQLite'a yazılır; özel rubrik veya hazır proje kodu üretilmez. Aynı/etkilenen boyuttaki sonraki açıklamalar yardımlı (`ASSISTED`) sayılırken önceden verilmiş yardımsız (`UNASSISTED`) yanıtlar korunur.
6. Hatalı soru `.codex/Invoke-ProjectAuditor.ps1 -Action void-doc-question -SessionId DDS-... -ExamId DBATCH-... -QuestionId DQ-... -Reason "..." [-AttemptId DTURN-...]` ile kullanıcı aleyhine sayılmadan iptal edilir. Belge sürümü değiştiğinde `.codex/Invoke-ProjectAuditor.ps1 -Action update-doc-version -SessionId DDS-... -DocumentVersion v1.1 -DocumentSha256 sha256:... [-Request <degisen_bolumler.json>] [-AttemptId DTURN-...]` eski kayıtları değiştirmeden yeni sürümü kaydeder ve değişen bölümleri önceki yardım geçmişini koruyarak yeniden `OPEN` durumuna alır. Oturum `-Action pause-doc-session -SessionId DDS-...`, `-Action resume-doc-session -SessionId DDS-...` ve `-Action stop-doc-session -SessionId DDS-...` ile duraklatılıp kaldığı yerden (`resume_manifest`, kapsam ve yardım geçmişiyle) sürdürülebilir.

`state` ve `doc-state` çıktıları özel orkestratör hazırlığıdır: değişmez ölçütleri içerebilir ve kullanıcıya aynen gösterilmez. `run` varsayılan çıktısı özel motor nesnesini dışlar. Kod içindeki `engine_output` Morks'un iç kullanımı içindir. Hata/ret durumunda kullanıcıya soru veya ipucu çıkarılmamalıdır.

## Yerel girişler

- Launcher: `.codex/Invoke-ProjectAuditor.ps1`.
- Python modülü: `.codex/scripts/project_auditor_runtime/`.
- Native rol kaydı: `.codex/agents/proje-denetleyici-ve-ogrenim-sorgulayicisi.toml`; `.codex/config.toml` rol anahtarı `proje_denetcisi_ve_ogrenim_sorgulayicisi`.
- Çalışma ortamı: `.codex/.venv-project-auditor/Scripts/python.exe`.
- Bağımlılıklar: paket içindeki `requirements.txt`. Ortam yoksa Morks `python -m venv .codex/.venv-project-auditor` ve ortamın Python'u ile requirements kurulumunu yürütür. Kullanıcıdan parola/API anahtarı istenmez.
- Kalıcı yerel SQLite: `.codex/scripts/.state/project-auditor/project_auditor.sqlite3`. Git dışında tutulur; kod savunması tabloları (`ledgers`, `ledger_events`, `exams`, `exam_questions`, `exam_responses`) ile belge savunması tablolarını (`doc_defense_sessions`, `doc_defense_scope_items`, `doc_defense_batches`, `doc_defense_questions`, `doc_defense_responses`, `doc_defense_events`) ayrı şemalarda tutar. Kullanıcı proje verilerini dışarıda yayımlama izni değildir.
- Kabul testleri ayrı geçici durum dizinlerinde çalışır; gerçek yardım geçmişini test için sıfırlama veya temizleme.

## Model ve çalıştırıcı seçimi

Varsayılan motor ve özel semantik inceleyici **GPT-6.1 Sol/high** kullanır. Windows'ta masaüstü uygulamasının paketlediği CLI, eski PATH/bağımsız CLI'den önce seçilir. Gerekirse yetkili orkestratör `HARMANOS_CODEX_EXECUTABLE` ile tam çalıştırıcı yolunu açıkça seçebilir; bu modelin kendisini değiştirmez.

16 Ekim incelemesinde eski bağımsız `codex-cli 0.153.4`, GPT-6.1 Sol'u reddetti; masaüstünün `0.162.0-alpha.17.2` çalıştırıcısı kataloğunda model vardı. Model erişimini eski çalıştırıcının hatasına göre yok sayma. Kullanıcının ana model ayarını veya mevcut beş ajanı bu yüzden değiştirme.

Taşıma kasanın dışında geçici dizinde, kullanıcı yapılandırması yüklenmeden ve hook'lar kapalı çalışır. Model araç olayları reddedilir; araçsız çalışmanın somut çağrı kanıtı kabul raporunda ayrıca tutulur. Bilinmeyen çağrılabilir olay türü güvenli varsayılmaz. API anahtarı eklenmez; mevcut yerel ChatGPT oturumu kullanılır. (Not: Araçsız çalışma ve yerel CLI yürütmesi, istem yükünün seçilen model sağlayıcısına iletilmediği anlamına gelmez; özel verinin sağlayıcıya aktarımı hakkında doğrulanmamış güvence verilmez.)

## Güvenlik ve kabul sınırı

Semantik inceleme, özel ölçütler ve daha önce açılan ipuçlarıyla birlikte yapılır. Eksik/belirsiz incelemede teslim durur. Regex ve şema tek başına anlamsal sızıntıyı garantiyle engellemez. Model çalışırken yardım günlüğü değişirse eski paket yeniden kabul edilmez.

Kod savunması tasarım kabulü [[Altıncı Uzman Ajan — v1.2 Tasarım Kabulü — 2026-10-16]], gerçek uygulama kabulü [[Altıncı Uzman Ajan — Runtime Kabulü — 2026-10-16]] içindedir. Proje ve belge savunması uzantısı (`PROJECT_DEFENSE_CONTRACT.md`, `PROMPT.md` Bölüm 9 ve çalışma katmanı) Morks bağımsız incelemesinde 71/71 test ve R1/R2 karşıörnek kontrolüyle kabul edilmiştir: [[Altıncı Uzman Ajan — Belge Savunması Nihai Kabulü — 2026-10-17]].

Native profil desteklenen ayarlarla yeniden düzenlendi; yalnız `enabled=false` içeren eksik MCP taşıma tanımları kaldırıldı. Native profil, kabul edilmiş PROMPT metnini kendi `developer_instructions` alanına taşır; güncel model/çaba ve özellik kısıtları dosyada bulunur. Taze CLI oturumunda yalnız çocuk rolün bildiği geçici bir kabul işaretinin doğru çıktıdan gelmesiyle rol dosyasının gerçekten uygulandığı doğrulandı; test değişikliği birebir geri alındı.

Bu sohbetin başlangıçta yüklenen yerleşik rol listesi sıcak yenilenmediğinden doğrudan native `agent_type` çağrısı hâlâ eski listeye bağlı olabilir. Bu, mevcut sohbette kontrollü launcher yolunu kullanmaya engel değildir. Morks bütün gerçek kullanıcı teslimini bu yoldan yapar; native profilin ham çıktısını teslim denetimi olmadan kullanıcıya iletmez. Görsel yan panel/rol listesi ayrıca gözlemlenmiş sayılmaz.
