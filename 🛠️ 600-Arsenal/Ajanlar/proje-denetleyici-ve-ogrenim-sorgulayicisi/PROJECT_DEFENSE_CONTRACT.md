---
title: "Proje Denetleyici ve Öğrenim Sorgulayıcısı — Proje ve Belge Savunması Sözleşmesi (PROJECT_DEFENSE_CONTRACT)"
created: 2026-10-17
modified: 2026-10-17
type: agent-contract
status: implementation-ready
version: "1.3"
agent_id: proje-denetleyici-ve-ogrenim-sorgulayicisi
tags:
  - harmanos
  - arsenal
  - ajan
  - proje-denetleyici
  - belge-savunmasi
  - sozlesme
---

# Proje Denetleyici ve Öğrenim Sorgulayıcısı — Proje ve Belge Savunması Sözleşmesi (`v1.3`)

Bu sözleşme, mevcut altıncı uzman ajan olan **Proje Denetleyici ve Öğrenim Sorgulayıcısı** (`proje-denetleyici-ve-ogrenim-sorgulayicisi`) içinde kod savunması (`PREPARE_EXAM` / `ANALYZE_RESPONSE` — `CONTRACT.md` `v1.2`) ile yan yana çalışan **Proje ve Belge Savunması (`PREPARE_PROJECT_DEFENSE` / `ANALYZE_PROJECT_DEFENSE`)** işlem yolunun tek otoritatif şema, doğrulama, teslim ve durum kurallarını tanımlar.

---

## 1. Mimari Sınırlar ve Araştırma Düzeltmeleri

1. **Tek Ajan, Ayrı Oturum ve Ayrı Sözleşme:**
   - Yeni veya yedinci bir ajan kurulmaz. Aynı ajan kimliği (`proje-denetleyici-ve-ogrenim-sorgulayicisi`) korunur ve tüm çağrılar Morks orkestrasyonu üzerinden yürütülür.
   - Belge savunması ve kod savunması aynı `project_id` değerine bağlanabilir ancak **ayrı oturumlarda** (`defense_session_id` vs. kod savunması `exam_id`/`attempt_id`) yürütülür.
   - Mevcut kod savunması sözleşmesi (`harmanos.project_auditor.input.v1` / `harmanos.project_auditor.output.v1`) ve `session_mode` alanı başka anlamda yeniden kullanılmaz; belge pasajları asla kod satırı (`start_line`/`end_line`) gibi gösterilmez.
2. **Araştırma Kaynakları ve Metodolojik Sınırlar:**
   - **Kaynak ile çıkarım ayrımı (SocraticLM):** SocraticLM çalışmasının doğru birincil kaynağı NeurIPS 2024 yayınıdır ([SocraticLM — NeurIPS 2024](https://papers.nips.cc/paper_files/paper/2024/hash/9bae399d1f34b8650351c1bd3692aeae-Abstract-Conference.html)). Yayındaki *Dean–Teacher–Student* kurgusu çok-turlu diyalog verisi üretmek için tasarlanmış bir **veri üretim hattıdır**; HarmanOS'un tek-ajan/orkestratör çalışma mimarisini doğrudan doğrulayan bir çalışma zamanı kanıtı değildir.
   - **Rubrik güvenilirlik sınırı (Prometheus):** [Prometheus](https://arxiv.org/abs/2310.08491) bulguları belirli model, referans materyal ve deney koşullarına aittir. Rubrik kullanımı tek başına doğruluk veya güvenilirlik garantisi sayılmaz; ajanın doğruluğu kendi deterministik doğrulayıcısı ve kabul örnekleriyle ölçülür.
   - **Araçsız çalışma, yerel CLI ve veri gizliliği ayrımı:** Çalışma zamanı (`CodexBackend`) araçsız (`tools=[]`), geçici dizinli (`--ephemeral`) ve salt-okunur (`--sandbox read-only`) yerel CLI çağrısı yapar; ancak yerel CLI üzerinden abonelik modeli çağırmak ile modeli tamamen yerelde (offline ağırlıklarla) çalıştırmak aynı şey değildir. Özel proje verisinin model sağlayıcısına aktarımı hakkında doğrulanmamış "sıfır dış aktarım" güvencesi verilmez.
   - **Dış kaynak doğrulaması ve sorgu mahremiyeti:** Belge dışı teknik bir iddianın doğrulanması gerektiğinde (`PENDING_EXTERNAL_VERIFICATION`), doğrulama ajan tarafından değil Morks tarafından herkese açık birincil kaynaklarla yapılır. Arama sorgusuna (`sanitized_public_search_topic`) özel proje metni, proje kimliği veya belge pasajı taşınmaz.

---

## 2. Kapsam, Bölüm Envanteri ve Boyut Durumları

1. **Belge Türleri ve İddia Epistemik Durumları:**
   - Belge türleri (`document_type`): `IDEA_PROPOSAL` (kodsuz fikir/başvuru belgesi), `ARCHITECTURE_SPEC` (mimari tasarım), `README_OR_DESIGN_DOC` (README/tasarım notu), `HYBRID_SPEC` (karma proje belgesi).
   - Her pasajdaki iddianın durumu (`claim_epistemic_status`): `IDEA` (fikir), `PLAN` (plan), `IMPLEMENTED` (uygulama), `MEASURED_RESULT` (ölçülmüş sonuç).
   - Kanıt dayanağı (`evidence_basis`): `USER_DECLARATION` (kullanıcı beyanı), `OBSERVED_EVIDENCE` (gözlenmiş kanıt), `MIXED` (karma). Uygulanmamış veya yalnız kullanıcı beyanına dayanan iddialar ölçülmüş sonuç gibi kabul edilmez.
2. **Bölüm Bölüm İşleme ve Görünürlük:**
   - Morks tam belge envanterini (`full_section_inventory`) çıkarır. Uzun belgeler sıralı bölüm grupları (`batch_index` / `total_batches`) halinde işlenir; sessiz kesme veya özetle kaynak pasajı değiştirme yapılmaz.
   - İncelenmeyen bölümler (`in_current_batch: false`) hem görev paketinde hem de çıktıdaki `uninspected_section_ids` alanında açıkça görünür kalır.
   - İçeriği okunamayan görsel/diyagram barındıran bölümler (`has_unreadable_visuals: true`) `waiting_visual_section_ids` altında beklemeye alınır ve `UNREADABLE_VISUAL_SCOPE_DEFERRED` sınırlamasıyla işaretlenir.
3. **Bölüm Boyutları ve Durumları:**
   - Her bölüm için ilgili boyutlar (`relevant_dimensions`):
     - `PROBLEM` (problem tanımı ve bağlam)
     - `METHOD` (yöntem ve çözüm akışı)
     - `DECISIONS_AND_TRADEOFFS` (tercihler ve ödünleşimler)
     - `ASSUMPTIONS` (varsayımlar)
     - `BOUNDARIES_AND_RISKS` (sınırlar, hata modları ve riskler)
     - `SUCCESS_METRICS` (başarı ölçütleri ve doğrulama)
   - Her boyut (`section_dimension_matrix`) şu dört durumdan birini alır:
     - `INSPECTED` (*incelendi*)
     - `OPEN` (*açık*)
     - `ADDRESSED_WITH_TEACHING` (*öğretimle ele alındı*)
     - `OUT_OF_SCOPE` (*kapsam dışı*)
4. **Sonuç Kategorileri ve Yönetişim Kilitleri:**
   - Sonuçlar yalnız üç kategoride kaydedilir (`defense_outcome_summary`):
     - `unassisted_explained_dimensions` (*yardımsız açıklanan boyutlar*)
     - `assisted_explained_dimensions` (*yardımla açıklanan boyutlar*)
     - `open_dimensions` (*açık kalan boyutlar*)
   - Genel başarı puanı (`overall_score_generated: false`), bağımsız uygulama yeterliği (`independent_competency_granted: false`, `eligible_for_independent_attempt_submission: false`) veya proje kapısı onayı (`project_gate_approval_granted: false`) **kesinlikle üretilmez**.

---

## 3. Otoritatif Girdi Şeması (`harmanos.project_auditor.doc_defense.input.v1`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://harmanos.local/schemas/project_auditor.doc_defense.input.v1.json",
  "title": "HarmanOS Project Auditor Document Defense Input v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "task_id",
    "as_of",
    "operation",
    "project_id",
    "defense_session_id",
    "learning_domain",
    "allowed_assistance_level",
    "tool_permissions",
    "document_descriptor",
    "full_section_inventory",
    "current_batch_passages",
    "contribution_context",
    "session_state_snapshot",
    "prior_defense_batch_package",
    "defense_responses"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "harmanos.project_auditor.doc_defense.input.v1"
    },
    "task_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9._-]{3,64}$"
    },
    "as_of": {
      "type": "string",
      "format": "date-time"
    },
    "operation": {
      "type": "string",
      "enum": [
        "PREPARE_PROJECT_DEFENSE",
        "ANALYZE_PROJECT_DEFENSE"
      ]
    },
    "project_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9._-]{3,64}$"
    },
    "defense_session_id": {
      "type": "string",
      "pattern": "^DDS-[A-Za-z0-9._-]{3,64}$"
    },
    "learning_domain": {
      "type": "string",
      "enum": [
        "SQL_DATA_ENG",
        "PYTHON_DATA_ENG",
        "PYTHON_CORE_PE1",
        "R_STATS",
        "SPSS_STATS",
        "CYBERSEC_UNI",
        "HARMANOS_SYSTEM_ARCH",
        "PROJECT_ARCHITECTURE_GENERAL",
        "C_PROGRAMMING",
        "42_PISCINE"
      ]
    },
    "allowed_assistance_level": {
      "type": "string",
      "enum": [
        "QUESTION_ONLY",
        "QUESTION_AND_CONCEPTUAL_HINT",
        "SILENT_OBSERVATION_ONLY"
      ]
    },
    "tool_permissions": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "allowed_tools",
        "code_execution_allowed",
        "mutation_allowed",
        "web_or_mcp_allowed",
        "subagent_invocation_allowed"
      ],
      "properties": {
        "allowed_tools": {
          "type": "array",
          "maxItems": 0,
          "items": false
        },
        "code_execution_allowed": {
          "type": "boolean",
          "const": false
        },
        "mutation_allowed": {
          "type": "boolean",
          "const": false
        },
        "web_or_mcp_allowed": {
          "type": "boolean",
          "const": false
        },
        "subagent_invocation_allowed": {
          "type": "boolean",
          "const": false
        }
      }
    },
    "document_descriptor": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "document_id",
        "document_title",
        "document_type",
        "document_version",
        "document_sha256",
        "prior_document_version",
        "prior_document_sha256",
        "document_summary",
        "batch_index",
        "total_batches"
      ],
      "properties": {
        "document_id": {
          "type": "string",
          "pattern": "^DOC-[A-Za-z0-9._-]{2,64}$"
        },
        "document_title": {
          "type": "string",
          "minLength": 1,
          "maxLength": 240
        },
        "document_type": {
          "type": "string",
          "enum": [
            "IDEA_PROPOSAL",
            "ARCHITECTURE_SPEC",
            "README_OR_DESIGN_DOC",
            "HYBRID_SPEC"
          ]
        },
        "document_version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "document_sha256": {
          "type": "string",
          "pattern": "^sha256:[a-f0-9]{64}$"
        },
        "prior_document_version": {
          "type": [
            "string",
            "null"
          ],
          "minLength": 1,
          "maxLength": 64
        },
        "prior_document_sha256": {
          "type": [
            "string",
            "null"
          ],
          "pattern": "^sha256:[a-f0-9]{64}$"
        },
        "document_summary": {
          "type": "string",
          "minLength": 1,
          "maxLength": 2000
        },
        "batch_index": {
          "type": "integer",
          "minimum": 1,
          "maximum": 64
        },
        "total_batches": {
          "type": "integer",
          "minimum": 1,
          "maximum": 64
        }
      }
    },
    "full_section_inventory": {
      "type": "array",
      "minItems": 1,
      "maxItems": 64,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "section_id",
          "ordinal",
          "heading_path",
          "section_sha256",
          "in_current_batch",
          "has_unreadable_visuals",
          "unreadable_visual_note",
          "relevant_dimensions",
          "prior_dimension_statuses"
        ],
        "properties": {
          "section_id": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          },
          "ordinal": {
            "type": "integer",
            "minimum": 1,
            "maximum": 64
          },
          "heading_path": {
            "type": "string",
            "minLength": 1,
            "maxLength": 240
          },
          "section_sha256": {
            "type": "string",
            "pattern": "^sha256:[a-f0-9]{64}$"
          },
          "in_current_batch": {
            "type": "boolean"
          },
          "has_unreadable_visuals": {
            "type": "boolean"
          },
          "unreadable_visual_note": {
            "type": [
              "string",
              "null"
            ],
            "maxLength": 500
          },
          "relevant_dimensions": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "uniqueItems": true,
            "items": {
              "type": "string",
              "enum": [
                "PROBLEM",
                "METHOD",
                "DECISIONS_AND_TRADEOFFS",
                "ASSUMPTIONS",
                "BOUNDARIES_AND_RISKS",
                "SUCCESS_METRICS"
              ]
            }
          },
          "prior_dimension_statuses": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "dimension",
                "status"
              ],
              "properties": {
                "dimension": {
                  "type": "string",
                  "enum": [
                    "PROBLEM",
                    "METHOD",
                    "DECISIONS_AND_TRADEOFFS",
                    "ASSUMPTIONS",
                    "BOUNDARIES_AND_RISKS",
                    "SUCCESS_METRICS"
                  ]
                },
                "status": {
                  "type": "string",
                  "enum": [
                    "INSPECTED",
                    "OPEN",
                    "ADDRESSED_WITH_TEACHING",
                    "OUT_OF_SCOPE"
                  ]
                }
              }
            }
          }
        }
      }
    },
    "current_batch_passages": {
      "type": "array",
      "minItems": 1,
      "maxItems": 24,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "passage_id",
          "section_id",
          "heading_path",
          "verbatim_text",
          "passage_sha256",
          "completeness",
          "claim_epistemic_status",
          "evidence_basis",
          "observed_evidence_refs",
          "cross_section_refs"
        ],
        "properties": {
          "passage_id": {
            "type": "string",
            "pattern": "^PSG-[A-Za-z0-9._-]{1,48}$"
          },
          "section_id": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          },
          "heading_path": {
            "type": "string",
            "minLength": 1,
            "maxLength": 240
          },
          "verbatim_text": {
            "type": "string",
            "minLength": 1,
            "maxLength": 16384
          },
          "passage_sha256": {
            "type": "string",
            "pattern": "^sha256:[a-f0-9]{64}$"
          },
          "completeness": {
            "type": "string",
            "enum": [
              "COMPLETE",
              "UNREADABLE_VISUAL_ONLY"
            ]
          },
          "claim_epistemic_status": {
            "type": "string",
            "enum": [
              "IDEA",
              "PLAN",
              "IMPLEMENTED",
              "MEASURED_RESULT"
            ]
          },
          "evidence_basis": {
            "type": "string",
            "enum": [
              "USER_DECLARATION",
              "OBSERVED_EVIDENCE",
              "MIXED"
            ]
          },
          "observed_evidence_refs": {
            "type": "array",
            "maxItems": 16,
            "items": {
              "type": "string",
              "minLength": 1,
              "maxLength": 200
            }
          },
          "cross_section_refs": {
            "type": "array",
            "maxItems": 16,
            "uniqueItems": true,
            "items": {
              "type": "string",
              "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
            }
          }
        }
      }
    },
    "contribution_context": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "prepared_by_morks_from_records",
        "team_structure",
        "user_role_summary",
        "declared_owned_section_ids",
        "delegated_or_teammate_section_ids",
        "prior_assistance_and_help_summary",
        "missing_contribution_fields"
      ],
      "properties": {
        "prepared_by_morks_from_records": {
          "type": "boolean",
          "const": true
        },
        "team_structure": {
          "type": "string",
          "enum": [
            "SOLO",
            "TEAM",
            "UNKNOWN"
          ]
        },
        "user_role_summary": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 500
        },
        "declared_owned_section_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          }
        },
        "delegated_or_teammate_section_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          }
        },
        "prior_assistance_and_help_summary": {
          "type": [
            "string",
            "null"
          ],
          "maxLength": 1000
        },
        "missing_contribution_fields": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "enum": [
              "TEAM_STRUCTURE",
              "USER_ROLE",
              "SECTION_OWNERSHIP",
              "EXTERNAL_OR_AI_ASSISTANCE"
            ]
          }
        }
      }
    },
    "session_state_snapshot": {
      "type": "object",
      "additionalProperties": false,
      "required": [
        "defense_session_id",
        "project_id",
        "session_revision",
        "session_status",
        "current_document_version",
        "current_document_sha256",
        "delivered_question_ids",
        "voided_question_ids",
        "disclosed_hint_ids",
        "taught_dimensions",
        "unassisted_explained_dimensions",
        "assisted_explained_dimensions"
      ],
      "properties": {
        "defense_session_id": {
          "type": "string",
          "pattern": "^DDS-[A-Za-z0-9._-]{3,64}$"
        },
        "project_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9._-]{3,64}$"
        },
        "session_revision": {
          "type": "integer",
          "minimum": 1
        },
        "session_status": {
          "type": "string",
          "enum": [
            "ACTIVE",
            "PAUSED",
            "COMPLETED",
            "STOPPED_BY_USER"
          ]
        },
        "current_document_version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "current_document_sha256": {
          "type": "string",
          "pattern": "^sha256:[a-f0-9]{64}$"
        },
        "delivered_question_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string"
          }
        },
        "voided_question_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string"
          }
        },
        "disclosed_hint_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string"
          }
        },
        "taught_dimensions": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "section_id",
              "dimension",
              "teaching_event_id",
              "closed_question_id"
            ],
            "properties": {
              "section_id": {
                "type": "string",
                "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
              },
              "dimension": {
                "type": "string",
                "enum": [
                  "PROBLEM",
                  "METHOD",
                  "DECISIONS_AND_TRADEOFFS",
                  "ASSUMPTIONS",
                  "BOUNDARIES_AND_RISKS",
                  "SUCCESS_METRICS"
                ]
              },
              "teaching_event_id": {
                "type": "string"
              },
              "closed_question_id": {
                "type": "string"
              }
            }
          }
        },
        "unassisted_explained_dimensions": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "section_id",
              "dimension"
            ],
            "properties": {
              "section_id": {
                "type": "string",
                "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
              },
              "dimension": {
                "type": "string",
                "enum": [
                  "PROBLEM",
                  "METHOD",
                  "DECISIONS_AND_TRADEOFFS",
                  "ASSUMPTIONS",
                  "BOUNDARIES_AND_RISKS",
                  "SUCCESS_METRICS"
                ]
              }
            }
          }
        },
        "assisted_explained_dimensions": {
          "type": "array",
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "section_id",
              "dimension"
            ],
            "properties": {
              "section_id": {
                "type": "string",
                "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
              },
              "dimension": {
                "type": "string",
                "enum": [
                  "PROBLEM",
                  "METHOD",
                  "DECISIONS_AND_TRADEOFFS",
                  "ASSUMPTIONS",
                  "BOUNDARIES_AND_RISKS",
                  "SUCCESS_METRICS"
                ]
              }
            }
          }
        }
      }
    },
    "prior_defense_batch_package": {
      "type": [
        "object",
        "null"
      ],
      "additionalProperties": false,
      "required": [
        "batch_exam_id",
        "defense_session_id",
        "project_id",
        "document_id",
        "document_version",
        "document_sha256",
        "created_as_of",
        "registered_questions",
        "batch_package_sha256"
      ],
      "properties": {
        "batch_exam_id": {
          "type": "string",
          "pattern": "^DBATCH-[A-Za-z0-9._-]{3,64}$"
        },
        "defense_session_id": {
          "type": "string",
          "pattern": "^DDS-[A-Za-z0-9._-]{3,64}$"
        },
        "project_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9._-]{3,64}$"
        },
        "document_id": {
          "type": "string",
          "pattern": "^DOC-[A-Za-z0-9._-]{2,64}$"
        },
        "document_version": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "document_sha256": {
          "type": "string",
          "pattern": "^sha256:[a-f0-9]{64}$"
        },
        "created_as_of": {
          "type": "string",
          "format": "date-time"
        },
        "registered_questions": {
          "type": "array",
          "minItems": 1,
          "maxItems": 32,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "question_id",
              "parent_question_id",
              "section_id",
              "passage_id",
              "target_dimension",
              "claim_epistemic_status",
              "delivered_to_learner",
              "voided",
              "defense_record_closed",
              "immutable_criteria"
            ],
            "properties": {
              "question_id": {
                "type": "string",
                "pattern": "^(?:DQ-[0-9]{2}-[A-Z0-9_]{2,32}|FQ-DQ-[0-9]{2}-[A-Z0-9_]{2,32}-01)$"
              },
              "parent_question_id": {
                "type": [
                  "string",
                  "null"
                ],
                "pattern": "^DQ-[0-9]{2}-[A-Z0-9_]{2,32}$"
              },
              "section_id": {
                "type": "string",
                "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
              },
              "passage_id": {
                "type": "string",
                "pattern": "^PSG-[A-Za-z0-9._-]{1,48}$"
              },
              "target_dimension": {
                "type": "string",
                "enum": [
                  "PROBLEM",
                  "METHOD",
                  "DECISIONS_AND_TRADEOFFS",
                  "ASSUMPTIONS",
                  "BOUNDARIES_AND_RISKS",
                  "SUCCESS_METRICS"
                ]
              },
              "claim_epistemic_status": {
                "type": "string",
                "enum": [
                  "IDEA",
                  "PLAN",
                  "IMPLEMENTED",
                  "MEASURED_RESULT"
                ]
              },
              "delivered_to_learner": {
                "type": "boolean"
              },
              "voided": {
                "type": "boolean"
              },
              "defense_record_closed": {
                "type": "boolean"
              },
              "immutable_criteria": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {
                  "type": "object",
                  "additionalProperties": false,
                  "required": [
                    "criterion_id",
                    "criterion_text",
                    "required_depth"
                  ],
                  "properties": {
                    "criterion_id": {
                      "type": "string",
                      "pattern": "^DCRIT-Q[0-9]{2}-[0-9]{2}$"
                    },
                    "criterion_text": {
                      "type": "string",
                      "minLength": 5,
                      "maxLength": 600
                    },
                    "required_depth": {
                      "type": "string",
                      "enum": [
                        "CONCEPTUAL_REASONING",
                        "TRADEOFF_JUSTIFICATION",
                        "FAILURE_MODE_AWARENESS",
                        "METRIC_AND_BOUNDARY_LINK"
                      ]
                    }
                  }
                }
              }
            }
          }
        },
        "batch_package_sha256": {
          "type": "string",
          "pattern": "^[a-f0-9]{64}$"
        }
      }
    },
    "defense_responses": {
      "type": "array",
      "maxItems": 16,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "response_id",
          "turn_id",
          "question_id",
          "parent_question_id",
          "section_id",
          "passage_id",
          "target_dimension",
          "raw_response_text",
          "is_idk_declaration",
          "declared_design_change",
          "external_verification_outcome",
          "criterion_ids_to_evaluate"
        ],
        "properties": {
          "response_id": {
            "type": "string",
            "pattern": "^DRESP-[A-Za-z0-9._-]{3,64}$"
          },
          "turn_id": {
            "type": "string",
            "pattern": "^DTURN-[0-9]{8}-[0-9]{2,4}$"
          },
          "question_id": {
            "type": "string",
            "pattern": "^(?:DQ-[0-9]{2}-[A-Z0-9_]{2,32}|FQ-DQ-[0-9]{2}-[A-Z0-9_]{2,32}-01)$"
          },
          "parent_question_id": {
            "type": [
              "string",
              "null"
            ],
            "pattern": "^DQ-[0-9]{2}-[A-Z0-9_]{2,32}$"
          },
          "section_id": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          },
          "passage_id": {
            "type": "string",
            "pattern": "^PSG-[A-Za-z0-9._-]{1,48}$"
          },
          "target_dimension": {
            "type": "string",
            "enum": [
              "PROBLEM",
              "METHOD",
              "DECISIONS_AND_TRADEOFFS",
              "ASSUMPTIONS",
              "BOUNDARIES_AND_RISKS",
              "SUCCESS_METRICS"
            ]
          },
          "raw_response_text": {
            "type": "string",
            "maxLength": 8192
          },
          "is_idk_declaration": {
            "type": "boolean"
          },
          "declared_design_change": {
            "type": "boolean"
          },
          "external_verification_outcome": {
            "type": [
              "object",
              "null"
            ],
            "additionalProperties": false,
            "required": [
              "status",
              "primary_source_summary",
              "sanitized_query_used"
            ],
            "properties": {
              "status": {
                "type": "string",
                "enum": [
                  "VERIFIED_VALID",
                  "VERIFIED_INVALID",
                  "INCONCLUSIVE"
                ]
              },
              "primary_source_summary": {
                "type": "string",
                "minLength": 1,
                "maxLength": 1000
              },
              "sanitized_query_used": {
                "type": "string",
                "minLength": 1,
                "maxLength": 240
              }
            }
          },
          "criterion_ids_to_evaluate": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "uniqueItems": true,
            "items": {
              "type": "string",
              "pattern": "^DCRIT-Q[0-9]{2}-[0-9]{2}$"
            }
          }
        }
      }
    }
  }
}
```

---

## 4. Otoritatif Çıktı Şeması (`harmanos.project_auditor.doc_defense.output.v1`)

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "$id": "https://harmanos.local/schemas/project_auditor.doc_defense.output.v1.json",
  "title": "HarmanOS Project Auditor Document Defense Output v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "task_id",
    "as_of_evaluated",
    "operation_evaluated",
    "terminal_status",
    "error_code",
    "error_detail",
    "project_defense_scope_evaluation",
    "section_dimension_matrix",
    "analysis_limitations",
    "learner_visible_payload",
    "orchestrator_only_payload"
  ],
  "properties": {
    "schema_version": {
      "type": "string",
      "const": "harmanos.project_auditor.doc_defense.output.v1"
    },
    "task_id": {
      "type": "string",
      "pattern": "^[A-Za-z0-9._-]{3,64}$"
    },
    "as_of_evaluated": {
      "type": "string",
      "format": "date-time"
    },
    "operation_evaluated": {
      "type": [
        "string",
        "null"
      ],
      "enum": [
        "PREPARE_PROJECT_DEFENSE",
        "ANALYZE_PROJECT_DEFENSE",
        null
      ]
    },
    "terminal_status": {
      "type": "string",
      "enum": [
        "PROJECT_DEFENSE_PREPARED",
        "PARTIAL_PROJECT_DEFENSE_PREPARED",
        "PROJECT_DEFENSE_ANALYZED",
        "SILENT_OBSERVATION_COMPLETED",
        "PEDAGOGICAL_LOCK_TRIGGERED",
        "OUT_OF_SCOPE",
        "INSUFFICIENT_EVIDENCE",
        "CONFLICTING_EVIDENCE",
        "INVALID_INPUT_CONTRACT"
      ]
    },
    "error_code": {
      "type": [
        "string",
        "null"
      ],
      "enum": [
        null,
        "UNPARSEABLE_OR_MISSING_TASK_ID",
        "PAYLOAD_BOUNDS_EXCEEDED",
        "SCHEMA_OR_VERSION_MISMATCH",
        "TOOL_PERMISSION_VIOLATION",
        "UNKNOWN_DOMAIN_OR_LANGUAGE",
        "INVALID_SECTION_OR_PASSAGE_REF",
        "UNREGISTERED_QUESTION_OR_CRITERION_REF",
        "TRUSTED_SESSION_STATE_MISMATCH",
        "FORBIDDEN_DOMAIN_C_OR_42",
        "SOLUTION_LEAKAGE_PREVENTED",
        "EPISTEMIC_CLAIM_CONTRADICTION",
        "UNREADABLE_OR_MISSING_TARGET_EVIDENCE",
        "EMPTY_OR_UNUSABLE_RESPONSE"
      ]
    },
    "error_detail": {
      "type": [
        "string",
        "null"
      ],
      "maxLength": 600
    },
    "project_defense_scope_evaluation": {
      "type": [
        "object",
        "null"
      ],
      "additionalProperties": false,
      "required": [
        "project_id",
        "defense_session_id",
        "document_id",
        "document_version_evaluated",
        "document_sha256_evaluated",
        "document_type_evaluated",
        "evaluated_domain",
        "allowed_assistance_level_evaluated",
        "c_or_42_detected",
        "prior_assistance_preserved",
        "batch_index_evaluated",
        "total_batches_evaluated",
        "inspected_section_ids_in_batch",
        "uninspected_section_ids",
        "waiting_visual_section_ids",
        "missing_contribution_fields_to_ask"
      ],
      "properties": {
        "project_id": {
          "type": "string",
          "pattern": "^[A-Za-z0-9._-]{3,64}$"
        },
        "defense_session_id": {
          "type": "string",
          "pattern": "^DDS-[A-Za-z0-9._-]{3,64}$"
        },
        "document_id": {
          "type": "string",
          "pattern": "^DOC-[A-Za-z0-9._-]{2,64}$"
        },
        "document_version_evaluated": {
          "type": "string",
          "minLength": 1,
          "maxLength": 64
        },
        "document_sha256_evaluated": {
          "type": "string",
          "pattern": "^sha256:[a-f0-9]{64}$"
        },
        "document_type_evaluated": {
          "type": "string",
          "enum": [
            "IDEA_PROPOSAL",
            "ARCHITECTURE_SPEC",
            "README_OR_DESIGN_DOC",
            "HYBRID_SPEC"
          ]
        },
        "evaluated_domain": {
          "type": "string"
        },
        "allowed_assistance_level_evaluated": {
          "type": "string",
          "enum": [
            "QUESTION_ONLY",
            "QUESTION_AND_CONCEPTUAL_HINT",
            "SILENT_OBSERVATION_ONLY"
          ]
        },
        "c_or_42_detected": {
          "type": "boolean"
        },
        "prior_assistance_preserved": {
          "type": "boolean",
          "const": true
        },
        "batch_index_evaluated": {
          "type": "integer",
          "minimum": 1
        },
        "total_batches_evaluated": {
          "type": "integer",
          "minimum": 1
        },
        "inspected_section_ids_in_batch": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          }
        },
        "uninspected_section_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          }
        },
        "waiting_visual_section_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          }
        },
        "missing_contribution_fields_to_ask": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "enum": [
              "TEAM_STRUCTURE",
              "USER_ROLE",
              "SECTION_OWNERSHIP",
              "EXTERNAL_OR_AI_ASSISTANCE"
            ]
          }
        }
      }
    },
    "section_dimension_matrix": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "section_id",
          "dimension",
          "status",
          "status_reason"
        ],
        "properties": {
          "section_id": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          },
          "dimension": {
            "type": "string",
            "enum": [
              "PROBLEM",
              "METHOD",
              "DECISIONS_AND_TRADEOFFS",
              "ASSUMPTIONS",
              "BOUNDARIES_AND_RISKS",
              "SUCCESS_METRICS"
            ]
          },
          "status": {
            "type": "string",
            "enum": [
              "INSPECTED",
              "OPEN",
              "ADDRESSED_WITH_TEACHING",
              "OUT_OF_SCOPE"
            ]
          },
          "status_reason": {
            "type": "string",
            "enum": [
              "EXPLAINED_UNASSISTED",
              "EXPLAINED_WITH_ASSISTANCE",
              "AWAITING_BATCH_OR_QUESTION",
              "UNREADABLE_VISUAL_WAITING",
              "REQUIRES_FOLLOWUP_OR_VERIFICATION",
              "IDK_OR_UNEXPLAINED",
              "TEACHING_DELIVERED",
              "NOT_APPLICABLE_TO_SECTION"
            ]
          }
        }
      }
    },
    "analysis_limitations": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "limitation_code",
          "section_id",
          "passage_id",
          "detail"
        ],
        "properties": {
          "limitation_code": {
            "type": "string",
            "enum": [
              "UNREADABLE_VISUAL_SCOPE_DEFERRED",
              "UNINSPECTED_BATCH_SECTIONS_REMAIN",
              "UNIMPLEMENTED_OR_IDEA_ONLY_CLAIM",
              "USER_DECLARATION_WITHOUT_OBSERVED_EVIDENCE",
              "DOCUMENT_VERSION_UPDATED_PRIOR_RECORDS_PRESERVED",
              "EXTERNAL_PRIMARY_SOURCE_CHECK_REQUIRED"
            ]
          },
          "section_id": {
            "type": [
              "string",
              "null"
            ],
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          },
          "passage_id": {
            "type": [
              "string",
              "null"
            ],
            "pattern": "^PSG-[A-Za-z0-9._-]{1,48}$"
          },
          "detail": {
            "type": "string",
            "minLength": 5,
            "maxLength": 500
          }
        }
      }
    },
    "learner_visible_payload": {
      "type": [
        "object",
        "null"
      ],
      "additionalProperties": false,
      "required": [
        "canonical_initial_question_id",
        "initial_neutral_question",
        "uninspected_section_ids",
        "waiting_visual_section_ids",
        "active_scope_notice"
      ],
      "properties": {
        "canonical_initial_question_id": {
          "type": "string",
          "pattern": "^DQ-[0-9]{2}-[A-Z0-9_]{2,32}$"
        },
        "initial_neutral_question": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "question_id",
            "section_id",
            "passage_id",
            "heading_path",
            "target_dimension",
            "claim_epistemic_status",
            "neutral_question_prompt"
          ],
          "properties": {
            "question_id": {
              "type": "string",
              "pattern": "^DQ-[0-9]{2}-[A-Z0-9_]{2,32}$"
            },
            "section_id": {
              "type": "string",
              "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
            },
            "passage_id": {
              "type": "string",
              "pattern": "^PSG-[A-Za-z0-9._-]{1,48}$"
            },
            "heading_path": {
              "type": "string",
              "minLength": 1,
              "maxLength": 240
            },
            "target_dimension": {
              "type": "string",
              "enum": [
                "PROBLEM",
                "METHOD",
                "DECISIONS_AND_TRADEOFFS",
                "ASSUMPTIONS",
                "BOUNDARIES_AND_RISKS",
                "SUCCESS_METRICS"
              ]
            },
            "claim_epistemic_status": {
              "type": "string",
              "enum": [
                "IDEA",
                "PLAN",
                "IMPLEMENTED",
                "MEASURED_RESULT"
              ]
            },
            "neutral_question_prompt": {
              "type": "string",
              "minLength": 10,
              "maxLength": 600
            }
          }
        },
        "uninspected_section_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          }
        },
        "waiting_visual_section_ids": {
          "type": "array",
          "uniqueItems": true,
          "items": {
            "type": "string",
            "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
          }
        },
        "active_scope_notice": {
          "type": "string",
          "enum": [
            "TPL_DOC_NOTICE_FULL_BATCH_QUESTION_ONLY: Belge savunması kapsamında mevcut bölüm grubu için yalnız ilk nötr soru gösterilmiştir; bu oturumda ipucu kapalıdır (QUESTION_ONLY).",
            "TPL_DOC_NOTICE_FULL_BATCH_ON_DEMAND_HINTS: Belge savunması kapsamında mevcut bölüm grubu için yalnız ilk nötr soru gösterilmiştir; ipucu yalnızca talep edilirse açılır ve yardım kaydına işlenir.",
            "TPL_DOC_NOTICE_PARTIAL_OR_DEFERRED_SCOPE: İncelenmeyen bölümler ve/veya okunamayan görsel kapsamı görünür tutularak mevcut bölüm grubu için yalnız ilk nötr soru gösterilmiştir."
          ]
        }
      }
    },
    "orchestrator_only_payload": {
      "type": [
        "object",
        "null"
      ],
      "additionalProperties": false,
      "required": [
        "defense_questions",
        "defense_response_observations",
        "defense_outcome_summary"
      ],
      "properties": {
        "defense_questions": {
          "type": "array",
          "maxItems": 24,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "question_id",
              "section_id",
              "passage_id",
              "heading_path",
              "target_dimension",
              "claim_epistemic_status",
              "evidence_basis",
              "cross_section_refs",
              "addresses_missing_contribution",
              "neutral_question_prompt",
              "expected_explanation_criteria",
              "on_demand_hints"
            ],
            "properties": {
              "question_id": {
                "type": "string",
                "pattern": "^DQ-[0-9]{2}-[A-Z0-9_]{2,32}$"
              },
              "section_id": {
                "type": "string",
                "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
              },
              "passage_id": {
                "type": "string",
                "pattern": "^PSG-[A-Za-z0-9._-]{1,48}$"
              },
              "heading_path": {
                "type": "string",
                "minLength": 1,
                "maxLength": 240
              },
              "target_dimension": {
                "type": "string",
                "enum": [
                  "PROBLEM",
                  "METHOD",
                  "DECISIONS_AND_TRADEOFFS",
                  "ASSUMPTIONS",
                  "BOUNDARIES_AND_RISKS",
                  "SUCCESS_METRICS"
                ]
              },
              "claim_epistemic_status": {
                "type": "string",
                "enum": [
                  "IDEA",
                  "PLAN",
                  "IMPLEMENTED",
                  "MEASURED_RESULT"
                ]
              },
              "evidence_basis": {
                "type": "string",
                "enum": [
                  "USER_DECLARATION",
                  "OBSERVED_EVIDENCE",
                  "MIXED"
                ]
              },
              "cross_section_refs": {
                "type": "array",
                "uniqueItems": true,
                "items": {
                  "type": "string",
                  "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
                }
              },
              "addresses_missing_contribution": {
                "type": "boolean"
              },
              "neutral_question_prompt": {
                "type": "string",
                "minLength": 10,
                "maxLength": 600
              },
              "expected_explanation_criteria": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {
                  "type": "object",
                  "additionalProperties": false,
                  "required": [
                    "criterion_id",
                    "criterion_text",
                    "required_depth"
                  ],
                  "properties": {
                    "criterion_id": {
                      "type": "string",
                      "pattern": "^DCRIT-Q[0-9]{2}-[0-9]{2}$"
                    },
                    "criterion_text": {
                      "type": "string",
                      "minLength": 5,
                      "maxLength": 600
                    },
                    "required_depth": {
                      "type": "string",
                      "enum": [
                        "CONCEPTUAL_REASONING",
                        "TRADEOFF_JUSTIFICATION",
                        "FAILURE_MODE_AWARENESS",
                        "METRIC_AND_BOUNDARY_LINK"
                      ]
                    }
                  }
                }
              },
              "on_demand_hints": {
                "type": "array",
                "maxItems": 2,
                "items": {
                  "type": "object",
                  "additionalProperties": false,
                  "required": [
                    "hint_id",
                    "hint_order",
                    "conceptual_nudge"
                  ],
                  "properties": {
                    "hint_id": {
                      "type": "string",
                      "pattern": "^DH-[0-9]{2}-[0-9]{2}-[A-Z0-9_]{2,24}$"
                    },
                    "hint_order": {
                      "type": "integer",
                      "enum": [
                        1,
                        2
                      ]
                    },
                    "conceptual_nudge": {
                      "type": "string",
                      "minLength": 10,
                      "maxLength": 500
                    }
                  }
                }
              }
            }
          }
        },
        "defense_response_observations": {
          "type": "array",
          "maxItems": 16,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": [
              "response_id",
              "turn_id",
              "question_id",
              "parent_question_id",
              "section_id",
              "passage_id",
              "target_dimension",
              "evaluation_verdict",
              "assistance_classification_for_response",
              "criterion_evaluations",
              "followup_question",
              "external_verification_request",
              "teaching_transition_packet"
            ],
            "properties": {
              "response_id": {
                "type": "string",
                "pattern": "^DRESP-[A-Za-z0-9._-]{3,64}$"
              },
              "turn_id": {
                "type": "string",
                "pattern": "^DTURN-[0-9]{8}-[0-9]{2,4}$"
              },
              "question_id": {
                "type": "string",
                "pattern": "^(?:DQ-[0-9]{2}-[A-Z0-9_]{2,32}|FQ-DQ-[0-9]{2}-[A-Z0-9_]{2,32}-01)$"
              },
              "parent_question_id": {
                "type": [
                  "string",
                  "null"
                ],
                "pattern": "^DQ-[0-9]{2}-[A-Z0-9_]{2,32}$"
              },
              "section_id": {
                "type": "string",
                "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
              },
              "passage_id": {
                "type": "string",
                "pattern": "^PSG-[A-Za-z0-9._-]{1,48}$"
              },
              "target_dimension": {
                "type": "string",
                "enum": [
                  "PROBLEM",
                  "METHOD",
                  "DECISIONS_AND_TRADEOFFS",
                  "ASSUMPTIONS",
                  "BOUNDARIES_AND_RISKS",
                  "SUCCESS_METRICS"
                ]
              },
              "evaluation_verdict": {
                "type": "string",
                "enum": [
                  "DIRECT_CRITERION_MATCH",
                  "ALTERNATIVE_VALID_EXPLANATION",
                  "FLUENT_SUPERFICIAL_OR_EMPTY",
                  "VAGUE_OR_INCOMPLETE_NEEDS_FOLLOWUP",
                  "DESIGN_CHANGED_WITHOUT_RATIONALE",
                  "NOT_IN_DOCUMENT",
                  "TECHNICALLY_INCORRECT",
                  "UNVERIFIED_EXTERNAL_CLAIM",
                  "PENDING_EXTERNAL_VERIFICATION",
                  "IDK_DECLARED_READY_FOR_TEACHING"
                ]
              },
              "assistance_classification_for_response": {
                "type": "string",
                "enum": [
                  "UNASSISTED",
                  "ASSISTED_BY_HINT",
                  "ASSISTED_BY_PRIOR_TEACHING_IN_DIMENSION",
                  "ASSISTED_BY_PRIOR_HELP_RECORD",
                  "NOT_EXPLAINED"
                ]
              },
              "criterion_evaluations": {
                "type": "array",
                "minItems": 1,
                "maxItems": 4,
                "items": {
                  "type": "object",
                  "additionalProperties": false,
                  "required": [
                    "criterion_id",
                    "criterion_text",
                    "status",
                    "verbatim_response_excerpt",
                    "observation_note"
                  ],
                  "properties": {
                    "criterion_id": {
                      "type": "string",
                      "pattern": "^DCRIT-Q[0-9]{2}-[0-9]{2}$"
                    },
                    "criterion_text": {
                      "type": "string",
                      "minLength": 5,
                      "maxLength": 600
                    },
                    "status": {
                      "type": "string",
                      "enum": [
                        "DEMONSTRATED",
                        "ALTERNATIVE_DEMONSTRATED",
                        "PARTIAL_OR_VAGUE",
                        "NOT_DEMONSTRATED",
                        "CONTRADICTED",
                        "PENDING_VERIFICATION"
                      ]
                    },
                    "verbatim_response_excerpt": {
                      "type": [
                        "string",
                        "null"
                      ],
                      "maxLength": 500
                    },
                    "observation_note": {
                      "type": "string",
                      "minLength": 5,
                      "maxLength": 500
                    }
                  }
                }
              },
              "followup_question": {
                "type": [
                  "object",
                  "null"
                ],
                "additionalProperties": false,
                "required": [
                  "followup_question_id",
                  "parent_question_id",
                  "section_id",
                  "passage_id",
                  "target_dimension",
                  "followup_reason",
                  "neutral_followup_prompt"
                ],
                "properties": {
                  "followup_question_id": {
                    "type": "string",
                    "pattern": "^FQ-DQ-[0-9]{2}-[A-Z0-9_]{2,32}-01$"
                  },
                  "parent_question_id": {
                    "type": "string",
                    "pattern": "^DQ-[0-9]{2}-[A-Z0-9_]{2,32}$"
                  },
                  "section_id": {
                    "type": "string",
                    "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
                  },
                  "passage_id": {
                    "type": "string",
                    "pattern": "^PSG-[A-Za-z0-9._-]{1,48}$"
                  },
                  "target_dimension": {
                    "type": "string",
                    "enum": [
                      "PROBLEM",
                      "METHOD",
                      "DECISIONS_AND_TRADEOFFS",
                      "ASSUMPTIONS",
                      "BOUNDARIES_AND_RISKS",
                      "SUCCESS_METRICS"
                    ]
                  },
                  "followup_reason": {
                    "type": "string",
                    "enum": [
                      "CLARIFY_VAGUE_RESPONSE",
                      "DESIGN_DECISION_CHANGE_RATIONALE"
                    ]
                  },
                  "neutral_followup_prompt": {
                    "type": "string",
                    "minLength": 10,
                    "maxLength": 600
                  }
                }
              },
              "external_verification_request": {
                "type": [
                  "object",
                  "null"
                ],
                "additionalProperties": false,
                "required": [
                  "verification_id",
                  "claim_summary_abstract",
                  "sanitized_public_search_topic",
                  "primary_source_types_required"
                ],
                "properties": {
                  "verification_id": {
                    "type": "string",
                    "pattern": "^VER-[A-Za-z0-9._-]{3,48}$"
                  },
                  "claim_summary_abstract": {
                    "type": "string",
                    "minLength": 5,
                    "maxLength": 400
                  },
                  "sanitized_public_search_topic": {
                    "type": "string",
                    "minLength": 5,
                    "maxLength": 200
                  },
                  "primary_source_types_required": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 4,
                    "uniqueItems": true,
                    "items": {
                      "type": "string",
                      "enum": [
                        "OFFICIAL_DOCUMENTATION",
                        "STANDARD_SPECIFICATION",
                        "PEER_REVIEWED_PAPER",
                        "BENCHMARK_OR_RFC"
                      ]
                    }
                  }
                }
              },
              "teaching_transition_packet": {
                "type": [
                  "object",
                  "null"
                ],
                "additionalProperties": false,
                "required": [
                  "teaching_packet_id",
                  "closed_question_id",
                  "closed_response_id",
                  "section_id",
                  "target_dimension",
                  "concept_and_rationale_explanation",
                  "suggested_approaches",
                  "downstream_affected_dimensions"
                ],
                "properties": {
                  "teaching_packet_id": {
                    "type": "string",
                    "pattern": "^TEACH-[A-Za-z0-9._-]{3,48}$"
                  },
                  "closed_question_id": {
                    "type": "string"
                  },
                  "closed_response_id": {
                    "type": "string"
                  },
                  "section_id": {
                    "type": "string",
                    "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
                  },
                  "target_dimension": {
                    "type": "string",
                    "enum": [
                      "PROBLEM",
                      "METHOD",
                      "DECISIONS_AND_TRADEOFFS",
                      "ASSUMPTIONS",
                      "BOUNDARIES_AND_RISKS",
                      "SUCCESS_METRICS"
                    ]
                  },
                  "concept_and_rationale_explanation": {
                    "type": "string",
                    "minLength": 15,
                    "maxLength": 1200
                  },
                  "suggested_approaches": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 3,
                    "items": {
                      "type": "string",
                      "minLength": 10,
                      "maxLength": 500
                    }
                  },
                  "downstream_affected_dimensions": {
                    "type": "array",
                    "items": {
                      "type": "object",
                      "additionalProperties": false,
                      "required": [
                        "section_id",
                        "dimension"
                      ],
                      "properties": {
                        "section_id": {
                          "type": "string",
                          "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
                        },
                        "dimension": {
                          "type": "string",
                          "enum": [
                            "PROBLEM",
                            "METHOD",
                            "DECISIONS_AND_TRADEOFFS",
                            "ASSUMPTIONS",
                            "BOUNDARIES_AND_RISKS",
                            "SUCCESS_METRICS"
                          ]
                        }
                      }
                    }
                  }
                }
              }
            }
          }
        },
        "defense_outcome_summary": {
          "type": "object",
          "additionalProperties": false,
          "required": [
            "unassisted_explained_dimensions",
            "assisted_explained_dimensions",
            "open_dimensions",
            "governance_locks"
          ],
          "properties": {
            "unassisted_explained_dimensions": {
              "type": "array",
              "items": {
                "type": "object",
                "additionalProperties": false,
                "required": [
                  "section_id",
                  "dimension"
                ],
                "properties": {
                  "section_id": {
                    "type": "string",
                    "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
                  },
                  "dimension": {
                    "type": "string",
                    "enum": [
                      "PROBLEM",
                      "METHOD",
                      "DECISIONS_AND_TRADEOFFS",
                      "ASSUMPTIONS",
                      "BOUNDARIES_AND_RISKS",
                      "SUCCESS_METRICS"
                    ]
                  }
                }
              }
            },
            "assisted_explained_dimensions": {
              "type": "array",
              "items": {
                "type": "object",
                "additionalProperties": false,
                "required": [
                  "section_id",
                  "dimension",
                  "assistance_sources"
                ],
                "properties": {
                  "section_id": {
                    "type": "string",
                    "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
                  },
                  "dimension": {
                    "type": "string",
                    "enum": [
                      "PROBLEM",
                      "METHOD",
                      "DECISIONS_AND_TRADEOFFS",
                      "ASSUMPTIONS",
                      "BOUNDARIES_AND_RISKS",
                      "SUCCESS_METRICS"
                    ]
                  },
                  "assistance_sources": {
                    "type": "array",
                    "minItems": 1,
                    "uniqueItems": true,
                    "items": {
                      "type": "string",
                      "enum": [
                        "HINT_USED",
                        "TEACHING_DELIVERED",
                        "PRIOR_RECORDED_HELP"
                      ]
                    }
                  }
                }
              }
            },
            "open_dimensions": {
              "type": "array",
              "items": {
                "type": "object",
                "additionalProperties": false,
                "required": [
                  "section_id",
                  "dimension",
                  "open_reason"
                ],
                "properties": {
                  "section_id": {
                    "type": "string",
                    "pattern": "^SEC-[A-Za-z0-9._-]{1,48}$"
                  },
                  "dimension": {
                    "type": "string",
                    "enum": [
                      "PROBLEM",
                      "METHOD",
                      "DECISIONS_AND_TRADEOFFS",
                      "ASSUMPTIONS",
                      "BOUNDARIES_AND_RISKS",
                      "SUCCESS_METRICS"
                    ]
                  },
                  "open_reason": {
                    "type": "string",
                    "minLength": 3,
                    "maxLength": 240
                  }
                }
              }
            },
            "governance_locks": {
              "type": "object",
              "additionalProperties": false,
              "required": [
                "overall_score_generated",
                "independent_competency_granted",
                "project_gate_approval_granted",
                "eligible_for_independent_attempt_submission"
              ],
              "properties": {
                "overall_score_generated": {
                  "type": "boolean",
                  "const": false
                },
                "independent_competency_granted": {
                  "type": "boolean",
                  "const": false
                },
                "project_gate_approval_granted": {
                  "type": "boolean",
                  "const": false
                },
                "eligible_for_independent_attempt_submission": {
                  "type": "boolean",
                  "const": false
                }
              }
            }
          }
        }
      }
    }
  }
}
```

---

## 5. Deterministik Doğrulama ve Teslim Kuralları (`DOC-PRE`, `DOC-POST`, `DOC-DELIV`)

### 5.1 Ön-Uçuş Kuralları (`DOC-PRE-01` .. `DOC-PRE-10`)
- **`DOC-PRE-01` (`UNPARSEABLE_OR_MISSING_TASK_ID`):** Girdi tek bir sonlu UTF-8 JSON nesnesi olmalı, yinelenen anahtar (`duplicate key`) veya `NaN`/`Infinity` içermemeli ve geçerli `task_id` taşımalıdır.
- **`DOC-PRE-02` (`PAYLOAD_BOUNDS_EXCEEDED`):** Ham JSON boyutu `98304` baytı, bölüm envanteri `64` bölümü, mevcut grup pasajları `24` pasajı ve tekil pasaj metni (`verbatim_text`) `16384` karakteri aşamaz.
- **`DOC-PRE-03` (`SCHEMA_OR_VERSION_MISMATCH` / `TOOL_PERMISSION_VIOLATION` / `UNKNOWN_DOMAIN_OR_LANGUAGE`):** Girdi Draft 2020-12 şemasına ve gerçek RFC 3339 takvim zaman damgasına uymalıdır. `tool_permissions` altında herhangi bir araç izni verilmişse `TOOL_PERMISSION_VIOLATION` döner.
- **`DOC-PRE-04` (`INVALID_SECTION_OR_PASSAGE_REF`):**
  - `full_section_inventory` içindeki `section_id` ve `ordinal` değerleri (`1..N` ardışık) benzersiz olmalıdır.
  - Her bölümün `prior_dimension_statuses` listesi, o bölümün `relevant_dimensions` kümesiyle bire bir örtüşmelidir.
  - `current_batch_passages` içindeki her pasajın `section_id` değeri `full_section_inventory` içinde `in_current_batch: true` olan bir bölüme ait olmalı; `passage_sha256` değeri LF-normalize `verbatim_text` içeriğinin gerçek SHA-256 özetiyle eşleşmeli; `cross_section_refs` içindeki tüm bölüm kimlikleri `full_section_inventory` içinde var olmalıdır.
  - `in_current_batch: true` olan her bölüm (yalnız okunamayan görselden oluşan ve `has_unreadable_visuals: true` olanlar hariç) en az bir `COMPLETE` pasaj içermelidir.
- **`DOC-PRE-05` (`EPISTEMIC_CLAIM_CONTRADICTION`):**
  - Bir pasaj `claim_epistemic_status: "MEASURED_RESULT"` iken `evidence_basis: "USER_DECLARATION"` olamaz ve `observed_evidence_refs` boş bırakılamaz (ölçülmüş sonuç iddiası gözlenmiş kanıt referansı gerektirir; yalnız kullanıcı beyanı ise `IDEA` veya `PLAN` olarak sınıflandırılmalıdır).
  - `evidence_basis: "USER_DECLARATION"` iken `observed_evidence_refs` dolu olamaz; `OBSERVED_EVIDENCE` veya `MIXED` iken `observed_evidence_refs` boş olamaz.
- **`DOC-PRE-06` (`UNREGISTERED_QUESTION_OR_CRITERION_REF`):**
  - `PREPARE_PROJECT_DEFENSE` işleminde `prior_defense_batch_package` `null` ve `defense_responses` `[]` olmalıdır.
  - `ANALYZE_PROJECT_DEFENSE` işleminde `prior_defense_batch_package` dolu olmalı, kanonik SHA-256 özeti (`batch_package_sha256`) yerel güvenilir SQLite kaydıyla bire bir eşleşmeli; her yanıt teslim edilmiş (`delivered_to_learner: true`), iptal edilmemiş (`voided: false`) ve savunma kaydı henüz kapatılmamış (`defense_record_closed: false`) bir soruya başvurmalıdır.
  - Takip yanıtlarında (`parent_question_id != null`), takip sorusu `FQ-DQ-...-01` biçiminde olmalı ve üst soruya (`parent_question_id`) ait ilk yanıt SQLite'da mevcut ve değişmemiş olmalıdır.
- **`DOC-PRE-07` (`TRUSTED_SESSION_STATE_MISMATCH`):** `session_state_snapshot` alanı, yerel SQLite `doc_defense_sessions` ve ilişkili tablolardan okunan güvenilir oturum durumuyla bire bir eşleşmelidir. Oturum `PAUSED` veya `STOPPED_BY_USER` durumunda iken açık devam (`resume`) işlemi yapılmadan yeni soru hazırlanamaz veya teslim edilemez.
- **`DOC-PRE-08` (`FORBIDDEN_DOMAIN_C_OR_42` -> `OUT_OF_SCOPE`):** `learning_domain` `C_PROGRAMMING` veya `42_PISCINE` ise çağrı `OUT_OF_SCOPE` ile reddedilir.
- **`DOC-PRE-09` (`UNREADABLE_OR_MISSING_TARGET_EVIDENCE` -> `INSUFFICIENT_EVIDENCE`):** Mevcut gruptaki tüm pasajlar `UNREADABLE_VISUAL_ONLY` ise soru üretilemez; `INSUFFICIENT_EVIDENCE` döner.
- **`DOC-PRE-10` (`EMPTY_OR_UNUSABLE_RESPONSE` -> `INSUFFICIENT_EVIDENCE`):** `ANALYZE_PROJECT_DEFENSE` işleminde herhangi bir yanıt metni (`raw_response_text`) boşsa `EMPTY_OR_UNUSABLE_RESPONSE` döner.

### 5.2 Son-Uçuş Kuralları (`DOC-POST-01` .. `DOC-POST-12`)
- **`DOC-POST-01` (`INVALID_OUTPUT_SCHEMA`):** Çıktı geçerli tekil JSON nesnesi olmalı ve `harmanos.project_auditor.doc_defense.output.v1` şemasını sağlamalıdır.
- **`DOC-POST-02` (`INVALID_OUTPUT_STATUS` / `INVALID_OUTPUT_ECHO_MISMATCH`):**
  - Girdi kimlikleri (`task_id`, `as_of`, `operation`, `project_id`, `defense_session_id`, `document_id`, `document_version`, `document_sha256`, `document_type`, `learning_domain`, `allowed_assistance_level`, `batch_index`, `total_batches`) çıktıda bire bir yansıtılmalıdır.
  - `uninspected_section_ids` alanı, `full_section_inventory` içinde `in_current_batch: false` olan bölümlerle bire bir aynı olmalıdır (incelenmeyen bölümler gizlenemez).
  - `waiting_visual_section_ids` alanı, `has_unreadable_visuals: true` olan bölümlerle bire bir aynı olmalıdır.
  - `PREPARE_PROJECT_DEFENSE` işleminde `uninspected_section_ids` veya `waiting_visual_section_ids` boş değilse (ve `allowed_assistance_level != "SILENT_OBSERVATION_ONLY"` ise) `terminal_status` `PARTIAL_PROJECT_DEFENSE_PREPARED` olmalı; tüm bölümler mevcut grupta ve görseller tam okunabilir ise `PROJECT_DEFENSE_PREPARED` olmalıdır.
- **`DOC-POST-03` (`HINT_OR_QUESTION_CAP_VIOLATION`):**
  - `QUESTION_ONLY` modunda `on_demand_hints` boş (`[]`) olmalıdır.
  - `learner_visible_payload.active_scope_notice` deterministik olarak seçilmelidir (`PARTIAL_PROJECT_DEFENSE_PREPARED` -> `TPL_DOC_NOTICE_PARTIAL_OR_DEFERRED_SCOPE`, `QUESTION_ONLY` -> `TPL_DOC_NOTICE_FULL_BATCH_QUESTION_ONLY`, aksi halde `TPL_DOC_NOTICE_FULL_BATCH_ON_DEMAND_HINTS`).
- **`DOC-POST-04` (`DUPLICATE_OR_UNORDERED_OUTPUT_ID`):** Soru kimlikleri (`DQ-01-...`, `DQ-02-...`), ölçüt kimlikleri (`DCRIT-Q01-01`...) ve ipucu kimlikleri (`DH-01-01-...`) sıralı ve benzersiz olmalıdır.
- **`DOC-POST-05` (`OUT_OF_BOUNDS_SOURCE_REF`):**
  - Her sorunun `section_id`, `passage_id`, `claim_epistemic_status`, `evidence_basis` ve `cross_section_refs` alanları `current_batch_passages` içindeki `COMPLETE` bir pasajla bire bir eşleşmelidir.
  - `missing_contribution_fields_to_ask` alanı `contribution_context.missing_contribution_fields` ile bire bir aynı olmalıdır; eksik katkı alanı yoksa (`[]`) hiçbir soru `addresses_missing_contribution: true` olamaz.
- **`DOC-POST-06` (`CRITERION_MUTATION_DETECTED`):** `ANALYZE_PROJECT_DEFENSE` çıktısındaki her gözlem, güvenilir paket içindeki soru ve değişmez ölçütlerle (`immutable_criteria`) bire bir eşleşmeli; `verbatim_response_excerpt` doluysa yanıt metninde bire bir geçmelidir.
- **`DOC-POST-07` (`FOLLOWUP_RULE_VIOLATION`):**
  - Bir ana soru için en fazla **1** takip sorusu (`FQ-DQ-...-01`) üretilebilir. Yanıt zaten bir takip sorusuna (`parent_question_id != null`) verilmişse ikinci bir takip sorusu üretilemez (`followup_question` `null` olmalıdır).
  - `evaluation_verdict == "DESIGN_CHANGED_WITHOUT_RATIONALE"` ise ve yanıt ana soruya aitse `followup_question` zorunludur ve `followup_reason == "DESIGN_DECISION_CHANGE_RATIONALE"` olmalıdır.
  - `evaluation_verdict == "VAGUE_OR_INCOMPLETE_NEEDS_FOLLOWUP"` ise ve yanıt ana soruya aitse `followup_question` zorunludur ve `followup_reason == "CLARIFY_VAGUE_RESPONSE"` olmalıdır.
- **`DOC-POST-08` (`VISIBLE_PRIVATE_QUESTION_DESYNC`):** `learner_visible_payload.initial_neutral_question` özel listedeki ilk soruyla (`defense_questions[0]`) bire bir eşleşmeli; `uninspected_section_ids` ve `waiting_visual_section_ids` kapsam değerlendirmesiyle aynı olmalıdır.
- **`DOC-POST-09` (`EXTERNAL_VERIFICATION_BOUNDARY_VIOLATION`):**
  - `evaluation_verdict == "PENDING_EXTERNAL_VERIFICATION"` ise `external_verification_request` dolu olmalı; diğer tüm kararlarda `null` olmalıdır.
  - `sanitized_public_search_topic` içinde `project_id`, `document_id`, `document_title` veya belge pasajlarından/özetinden 24+ karakterlik bire bir özel metin kesiti bulunamaz (`PRIVATE_TEXT_IN_SEARCH_QUERY`).
  - Girdide `external_verification_outcome.status == "INCONCLUSIVE"` verilmişse model olumlu (`DIRECT_CRITERION_MATCH`, `ALTERNATIVE_VALID_EXPLANATION`) veya olumsuz (`TECHNICALLY_INCORRECT`) hüküm uyduramaz; `evaluation_verdict` zorunlu olarak `"UNVERIFIED_EXTERNAL_CLAIM"` olmalı ve ilgili boyut `OPEN` kalmalıdır.
- **`DOC-POST-10` (`TEACHING_TRANSITION_VIOLATION`):**
  - Yanıtta `is_idk_declaration: true` ise `evaluation_verdict` `"IDK_DECLARED_READY_FOR_TEACHING"` olmalı ve `teaching_transition_packet` dolu olmalıdır (`closed_question_id` ve `closed_response_id` yanıtla eşleşmelidir).
  - `teaching_transition_packet` içindeki açıklama ve yaklaşım önerileri özel rubrik metnini (`criterion_text`) bire bir sızdıramaz ve hazır proje kodu (`lexical_solution_leak`) içeremez.
- **`DOC-POST-11` (`ASSISTANCE_TAINT_OR_OUTCOME_MISMATCH`):**
  - Önceden `"TEACHING_DELIVERED"` olan veya aynı boyutta ipucu/yardım kaydı bulunan bir `(section_id, target_dimension)` için verilen sonraki açıklamalar asla `"UNASSISTED"` (`unassisted_explained_dimensions`) sayılamaz; açıklanmışsa `"ASSISTED_BY_PRIOR_TEACHING_IN_DIMENSION"` / `"ASSISTED_BY_HINT"` / `"ASSISTED_BY_PRIOR_HELP_RECORD"` olarak sınıflandırılmalı ve `assisted_explained_dimensions` altında yer almalıdır.
  - Öğretimden **önce** yardımsız açıklanmış olan boyutlar (`session_state_snapshot.unassisted_explained_dimensions`) yardımsız olarak korunmalıdır.
- **`DOC-POST-12` (`GOVERNANCE_LOCK_VIOLATION`):** `governance_locks` altındaki dört bayrak (`overall_score_generated`, `independent_competency_granted`, `project_gate_approval_granted`, `eligible_for_independent_attempt_submission`) her zaman `false` olmalıdır. `section_dimension_matrix` tüm `full_section_inventory` bölümlerinin `relevant_dimensions` çiftlerini eksiksiz kapsamalıdır.

---

## 6. Kanonik Kabul Örnekleri

### 6.1 Örnek 1 — `PREPARE_PROJECT_DEFENSE` Girdisi (Çok Bölümlü Mimari & Fikir Belgesi)

```json
{
  "schema_version": "harmanos.project_auditor.doc_defense.input.v1",
  "task_id": "DOCAUD-20261017-001",
  "as_of": "2026-10-17T14:30:00+03:00",
  "operation": "PREPARE_PROJECT_DEFENSE",
  "project_id": "PROJ-ROLELINT-TR",
  "defense_session_id": "DDS-ROLELINT-20261017-01",
  "learning_domain": "PYTHON_DATA_ENG",
  "allowed_assistance_level": "QUESTION_AND_CONCEPTUAL_HINT",
  "tool_permissions": {
    "allowed_tools": [],
    "code_execution_allowed": false,
    "mutation_allowed": false,
    "web_or_mcp_allowed": false,
    "subagent_invocation_allowed": false
  },
  "document_descriptor": {
    "document_id": "DOC-ROLELINT-ARCH-V1",
    "document_title": "RoleLint TR — İlan Ayrıştırma ve Aday Eşleştirme Mimari Tasarımı",
    "document_type": "ARCHITECTURE_SPEC",
    "document_version": "v1.0",
    "document_sha256": "sha256:4a8d1f7e5c3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a291",
    "prior_document_version": null,
    "prior_document_sha256": null,
    "document_summary": "Türkçe iş ilanlarından deterministik kural katmanı ve şema doğrulamalı çıkarım ile rol gereksinimlerini ayrıştıran yerel veri hattı tasarımı.",
    "batch_index": 1,
    "total_batches": 2
  },
  "full_section_inventory": [
    {
      "section_id": "SEC-01-PROBLEM",
      "ordinal": 1,
      "heading_path": "1. Problem Tanımı ve Kapsam Sınırları",
      "section_sha256": "sha256:ea51983f5c98900e6193c9a1f985f0d0c237157176d3c2a57cf125317b534277",
      "in_current_batch": true,
      "has_unreadable_visuals": false,
      "unreadable_visual_note": null,
      "relevant_dimensions": [
        "PROBLEM",
        "BOUNDARIES_AND_RISKS"
      ],
      "prior_dimension_statuses": [
        {
          "dimension": "PROBLEM",
          "status": "OPEN"
        },
        {
          "dimension": "BOUNDARIES_AND_RISKS",
          "status": "OPEN"
        }
      ]
    },
    {
      "section_id": "SEC-02-PIPELINE",
      "ordinal": 2,
      "heading_path": "2. İki Aşamalı Ayrıştırma Yöntemi ve Tercihler",
      "section_sha256": "sha256:3dcf04cab6c30c471c8b02540f64a44067e0d6d7f388900a836419a935e076be",
      "in_current_batch": true,
      "has_unreadable_visuals": true,
      "unreadable_visual_note": "Akış diyagramı (pipeline_v1.png) ikili görsel olarak eklendiği için metin katmanında okunamıyor.",
      "relevant_dimensions": [
        "METHOD",
        "DECISIONS_AND_TRADEOFFS",
        "ASSUMPTIONS"
      ],
      "prior_dimension_statuses": [
        {
          "dimension": "METHOD",
          "status": "OPEN"
        },
        {
          "dimension": "DECISIONS_AND_TRADEOFFS",
          "status": "OPEN"
        },
        {
          "dimension": "ASSUMPTIONS",
          "status": "OPEN"
        }
      ]
    },
    {
      "section_id": "SEC-03-EVALUATION",
      "ordinal": 3,
      "heading_path": "3. Başarı Ölçütleri ve Doğrulama Kümesi",
      "section_sha256": "sha256:9f8e7d6c5b4a392817263544536271809f8e7d6c5b4a39281726354453627180",
      "in_current_batch": false,
      "has_unreadable_visuals": false,
      "unreadable_visual_note": null,
      "relevant_dimensions": [
        "SUCCESS_METRICS"
      ],
      "prior_dimension_statuses": [
        {
          "dimension": "SUCCESS_METRICS",
          "status": "OPEN"
        }
      ]
    }
  ],
  "current_batch_passages": [
    {
      "passage_id": "PSG-01-PROBLEM-CORE",
      "section_id": "SEC-01-PROBLEM",
      "heading_path": "1. Problem Tanımı ve Kapsam Sınırları",
      "verbatim_text": "RoleLint TR, Türkçe veri ve yazılım ilanlarındaki muğlak beceri ifadelerini normalize ederek adayın doğrulanmış kanıtlarıyla karşılaştırır. Sistem yalnız çevrimdışı indirilen ilan metinlerini işler; canlı kazıma (scraping) ve otomatik başvuru kapsam dışıdır.",
      "passage_sha256": "sha256:ea51983f5c98900e6193c9a1f985f0d0c237157176d3c2a57cf125317b534277",
      "completeness": "COMPLETE",
      "claim_epistemic_status": "PLAN",
      "evidence_basis": "USER_DECLARATION",
      "observed_evidence_refs": [],
      "cross_section_refs": [
        "SEC-03-EVALUATION"
      ]
    },
    {
      "passage_id": "PSG-02-PIPELINE-TEXT",
      "section_id": "SEC-02-PIPELINE",
      "heading_path": "2. İki Aşamalı Ayrıştırma Yöntemi ve Tercihler",
      "verbatim_text": "İlk aşamada deterministik sözlük ve regex kurallarıyla zorunlu teknoloji etiketleri çıkarılır; ikinci aşamada ise yalnız belirsiz cümleler şema kısıtlı yerel modele gönderilir. Bu sayede her ilanda tam metin model çağrısı yapılmaz.",
      "passage_sha256": "sha256:3dcf04cab6c30c471c8b02540f64a44067e0d6d7f388900a836419a935e076be",
      "completeness": "COMPLETE",
      "claim_epistemic_status": "IDEA",
      "evidence_basis": "USER_DECLARATION",
      "observed_evidence_refs": [],
      "cross_section_refs": [
        "SEC-01-PROBLEM",
        "SEC-03-EVALUATION"
      ]
    }
  ],
  "contribution_context": {
    "prepared_by_morks_from_records": true,
    "team_structure": "SOLO",
    "user_role_summary": "Tasarım ve veri şeması sahibi (bireysel proje).",
    "declared_owned_section_ids": [
      "SEC-01-PROBLEM",
      "SEC-02-PIPELINE",
      "SEC-03-EVALUATION"
    ],
    "delegated_or_teammate_section_ids": [],
    "prior_assistance_and_help_summary": "Önceki oturumda yardım kaydı yok.",
    "missing_contribution_fields": []
  },
  "session_state_snapshot": {
    "defense_session_id": "DDS-ROLELINT-20261017-01",
    "project_id": "PROJ-ROLELINT-TR",
    "session_revision": 1,
    "session_status": "ACTIVE",
    "current_document_version": "v1.0",
    "current_document_sha256": "sha256:4a8d1f7e5c3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a291",
    "delivered_question_ids": [],
    "voided_question_ids": [],
    "disclosed_hint_ids": [],
    "taught_dimensions": [],
    "unassisted_explained_dimensions": [],
    "assisted_explained_dimensions": []
  },
  "prior_defense_batch_package": null,
  "defense_responses": []
}
```

### 6.2 Örnek 2 — `PREPARE_PROJECT_DEFENSE` Çıktısı (`PARTIAL_PROJECT_DEFENSE_PREPARED`)

```json
{
  "schema_version": "harmanos.project_auditor.doc_defense.output.v1",
  "task_id": "DOCAUD-20261017-001",
  "as_of_evaluated": "2026-10-17T14:30:00+03:00",
  "operation_evaluated": "PREPARE_PROJECT_DEFENSE",
  "terminal_status": "PARTIAL_PROJECT_DEFENSE_PREPARED",
  "error_code": null,
  "error_detail": null,
  "project_defense_scope_evaluation": {
    "project_id": "PROJ-ROLELINT-TR",
    "defense_session_id": "DDS-ROLELINT-20261017-01",
    "document_id": "DOC-ROLELINT-ARCH-V1",
    "document_version_evaluated": "v1.0",
    "document_sha256_evaluated": "sha256:4a8d1f7e5c3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a291",
    "document_type_evaluated": "ARCHITECTURE_SPEC",
    "evaluated_domain": "PYTHON_DATA_ENG",
    "allowed_assistance_level_evaluated": "QUESTION_AND_CONCEPTUAL_HINT",
    "c_or_42_detected": false,
    "prior_assistance_preserved": true,
    "batch_index_evaluated": 1,
    "total_batches_evaluated": 2,
    "inspected_section_ids_in_batch": [
      "SEC-01-PROBLEM",
      "SEC-02-PIPELINE"
    ],
    "uninspected_section_ids": [
      "SEC-03-EVALUATION"
    ],
    "waiting_visual_section_ids": [
      "SEC-02-PIPELINE"
    ],
    "missing_contribution_fields_to_ask": []
  },
  "section_dimension_matrix": [
    {
      "section_id": "SEC-01-PROBLEM",
      "dimension": "PROBLEM",
      "status": "OPEN",
      "status_reason": "AWAITING_BATCH_OR_QUESTION"
    },
    {
      "section_id": "SEC-01-PROBLEM",
      "dimension": "BOUNDARIES_AND_RISKS",
      "status": "OPEN",
      "status_reason": "AWAITING_BATCH_OR_QUESTION"
    },
    {
      "section_id": "SEC-02-PIPELINE",
      "dimension": "METHOD",
      "status": "OPEN",
      "status_reason": "UNREADABLE_VISUAL_WAITING"
    },
    {
      "section_id": "SEC-02-PIPELINE",
      "dimension": "DECISIONS_AND_TRADEOFFS",
      "status": "OPEN",
      "status_reason": "AWAITING_BATCH_OR_QUESTION"
    },
    {
      "section_id": "SEC-02-PIPELINE",
      "dimension": "ASSUMPTIONS",
      "status": "OPEN",
      "status_reason": "AWAITING_BATCH_OR_QUESTION"
    },
    {
      "section_id": "SEC-03-EVALUATION",
      "dimension": "SUCCESS_METRICS",
      "status": "OPEN",
      "status_reason": "AWAITING_BATCH_OR_QUESTION"
    }
  ],
  "analysis_limitations": [
    {
      "limitation_code": "UNREADABLE_VISUAL_SCOPE_DEFERRED",
      "section_id": "SEC-02-PIPELINE",
      "passage_id": "PSG-02-PIPELINE-TEXT",
      "detail": "SEC-02-PIPELINE içindeki akış diyagramı okunamadığından görsele bağlı yöntem akışı doğrulaması beklemeye alındı."
    },
    {
      "limitation_code": "UNINSPECTED_BATCH_SECTIONS_REMAIN",
      "section_id": "SEC-03-EVALUATION",
      "passage_id": null,
      "detail": "SEC-03-EVALUATION sonraki bölüm grubunda (Batch 2/2) incelenmek üzere görünür tutuldu."
    },
    {
      "limitation_code": "UNIMPLEMENTED_OR_IDEA_ONLY_CLAIM",
      "section_id": "SEC-02-PIPELINE",
      "passage_id": "PSG-02-PIPELINE-TEXT",
      "detail": "İki aşamalı ayrıştırma hattı henüz fikir/plan aşamasındadır; uygulanmış veya ölçülmüş sonuç sayılmaz."
    }
  ],
  "learner_visible_payload": {
    "canonical_initial_question_id": "DQ-01-SCOPE_BOUNDARY",
    "initial_neutral_question": {
      "question_id": "DQ-01-SCOPE_BOUNDARY",
      "section_id": "SEC-01-PROBLEM",
      "passage_id": "PSG-01-PROBLEM-CORE",
      "heading_path": "1. Problem Tanımı ve Kapsam Sınırları",
      "target_dimension": "BOUNDARIES_AND_RISKS",
      "claim_epistemic_status": "PLAN",
      "neutral_question_prompt": "1. bölümde sistemin yalnız çevrimdışı indirilen ilan metinlerini işleyeceği ve canlı kazımanın kapsam dışı bırakıldığı belirtiliyor. Bu sınır kararının arkasındaki temel teknik ve operasyonel gerekçeler nelerdir?"
    },
    "uninspected_section_ids": [
      "SEC-03-EVALUATION"
    ],
    "waiting_visual_section_ids": [
      "SEC-02-PIPELINE"
    ],
    "active_scope_notice": "TPL_DOC_NOTICE_PARTIAL_OR_DEFERRED_SCOPE: İncelenmeyen bölümler ve/veya okunamayan görsel kapsamı görünür tutularak mevcut bölüm grubu için yalnız ilk nötr soru gösterilmiştir."
  },
  "orchestrator_only_payload": {
    "defense_questions": [
      {
        "question_id": "DQ-01-SCOPE_BOUNDARY",
        "section_id": "SEC-01-PROBLEM",
        "passage_id": "PSG-01-PROBLEM-CORE",
        "heading_path": "1. Problem Tanımı ve Kapsam Sınırları",
        "target_dimension": "BOUNDARIES_AND_RISKS",
        "claim_epistemic_status": "PLAN",
        "evidence_basis": "USER_DECLARATION",
        "cross_section_refs": [
          "SEC-03-EVALUATION"
        ],
        "addresses_missing_contribution": false,
        "neutral_question_prompt": "1. bölümde sistemin yalnız çevrimdışı indirilen ilan metinlerini işleyeceği ve canlı kazımanın kapsam dışı bırakıldığı belirtiliyor. Bu sınır kararının arkasındaki temel teknik ve operasyonel gerekçeler nelerdir?",
        "expected_explanation_criteria": [
          {
            "criterion_id": "DCRIT-Q01-01",
            "criterion_text": "Canlı kazımanın getireceği DOM kırılganlığı, hız sınırı/erişim engeli veya hukuki/etik riskleri ayrıştırma çekirdeğinden izole etme gerekçesini açıklar.",
            "required_depth": "TRADEOFF_JUSTIFICATION"
          },
          {
            "criterion_id": "DCRIT-Q01-02",
            "criterion_text": "Çevrimdışı sabit metin girdisinin deterministik tekrar üretilebilirlik ve 3. bölümdeki değerlendirme kümesi tutarlılığı için sağladığı avantajı belirtir.",
            "required_depth": "METRIC_AND_BOUNDARY_LINK"
          }
        ],
        "on_demand_hints": [
          {
            "hint_id": "DH-01-01-REPRODUCIBILITY",
            "hint_order": 1,
            "conceptual_nudge": "Girdi verisinin zaman içinde değişebilen canlı sayfalar yerine sabit metin olarak alınmasının, 3. bölümdeki doğrulama ölçümlerinin tekrarlanabilirliğine etkisini düşünün."
          }
        ]
      },
      {
        "question_id": "DQ-02-HYBRID_TRADEOFF",
        "section_id": "SEC-02-PIPELINE",
        "passage_id": "PSG-02-PIPELINE-TEXT",
        "heading_path": "2. İki Aşamalı Ayrıştırma Yöntemi ve Tercihler",
        "target_dimension": "DECISIONS_AND_TRADEOFFS",
        "claim_epistemic_status": "IDEA",
        "evidence_basis": "USER_DECLARATION",
        "cross_section_refs": [
          "SEC-01-PROBLEM",
          "SEC-03-EVALUATION"
        ],
        "addresses_missing_contribution": false,
        "neutral_question_prompt": "2. bölümde ilk aşamada deterministik sözlük/regex, ikinci aşamada ise yalnız belirsiz cümleler için model çağrısı öneriliyor. İlk aşamanın yanlış negatif (bir gereksinimi belirsiz bile saymadan atlama) üretmesi durumunda ikinci aşamanın bunu telafi edememe riskini nasıl ele alıyorsunuz?",
        "expected_explanation_criteria": [
          {
            "criterion_id": "DCRIT-Q02-01",
            "criterion_text": "İlk aşamadaki filtreleme eşiğinin yüksek duyarlılık (recall) odaklı tutulması veya eşleşmeyen cümlelerin ikinci aşamaya devredilmesi gerekliliğini açıklar.",
            "required_depth": "FAILURE_MODE_AWARENESS"
          }
        ],
        "on_demand_hints": [
          {
            "hint_id": "DH-02-01-FALSE_NEGATIVE",
            "hint_order": 1,
            "conceptual_nudge": "Bir cümlenin ikinci aşamaya (modele) hangi koşulda gönderildiğini ve sözlükte yer almayan yeni bir teknoloji teriminin hangi yola düşeceğini düşünün."
          }
        ]
      }
    ],
    "defense_response_observations": [],
    "defense_outcome_summary": {
      "unassisted_explained_dimensions": [],
      "assisted_explained_dimensions": [],
      "open_dimensions": [
        {
          "section_id": "SEC-01-PROBLEM",
          "dimension": "PROBLEM",
          "open_reason": "Henüz yanıtlanmadı."
        },
        {
          "section_id": "SEC-01-PROBLEM",
          "dimension": "BOUNDARIES_AND_RISKS",
          "open_reason": "İlk soru olarak hazırlandı; yanıt bekleniyor."
        },
        {
          "section_id": "SEC-02-PIPELINE",
          "dimension": "METHOD",
          "open_reason": "Görsel diyagram okunamadığı için beklemeye alındı."
        },
        {
          "section_id": "SEC-02-PIPELINE",
          "dimension": "DECISIONS_AND_TRADEOFFS",
          "open_reason": "Soru hazırlandı; yanıt bekleniyor."
        },
        {
          "section_id": "SEC-02-PIPELINE",
          "dimension": "ASSUMPTIONS",
          "open_reason": "Henüz yanıtlanmadı."
        },
        {
          "section_id": "SEC-03-EVALUATION",
          "dimension": "SUCCESS_METRICS",
          "open_reason": "Sonraki bölüm grubunda (Batch 2/2) incelenecek."
        }
      ],
      "governance_locks": {
        "overall_score_generated": false,
        "independent_competency_granted": false,
        "project_gate_approval_granted": false,
        "eligible_for_independent_attempt_submission": false
      }
    }
  }
}
```

### 6.3 Örnek 3 — `ANALYZE_PROJECT_DEFENSE` Girdisi (Kısa Doğru Yanıt + Tasarım Değişikliği Bildirimi)

```json
{
  "schema_version": "harmanos.project_auditor.doc_defense.input.v1",
  "task_id": "DOCAUD-20261017-002",
  "as_of": "2026-10-17T14:40:00+03:00",
  "operation": "ANALYZE_PROJECT_DEFENSE",
  "project_id": "PROJ-ROLELINT-TR",
  "defense_session_id": "DDS-ROLELINT-20261017-01",
  "learning_domain": "PYTHON_DATA_ENG",
  "allowed_assistance_level": "QUESTION_AND_CONCEPTUAL_HINT",
  "tool_permissions": {
    "allowed_tools": [],
    "code_execution_allowed": false,
    "mutation_allowed": false,
    "web_or_mcp_allowed": false,
    "subagent_invocation_allowed": false
  },
  "document_descriptor": {
    "document_id": "DOC-ROLELINT-ARCH-V1",
    "document_title": "RoleLint TR — İlan Ayrıştırma ve Aday Eşleştirme Mimari Tasarımı",
    "document_type": "ARCHITECTURE_SPEC",
    "document_version": "v1.0",
    "document_sha256": "sha256:4a8d1f7e5c3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a291",
    "prior_document_version": null,
    "prior_document_sha256": null,
    "document_summary": "Türkçe iş ilanlarından deterministik kural katmanı ve şema doğrulamalı çıkarım ile rol gereksinimlerini ayrıştıran yerel veri hattı tasarımı.",
    "batch_index": 1,
    "total_batches": 2
  },
  "full_section_inventory": [
    {
      "section_id": "SEC-01-PROBLEM",
      "ordinal": 1,
      "heading_path": "1. Problem Tanımı ve Kapsam Sınırları",
      "section_sha256": "sha256:ea51983f5c98900e6193c9a1f985f0d0c237157176d3c2a57cf125317b534277",
      "in_current_batch": true,
      "has_unreadable_visuals": false,
      "unreadable_visual_note": null,
      "relevant_dimensions": [
        "PROBLEM",
        "BOUNDARIES_AND_RISKS"
      ],
      "prior_dimension_statuses": [
        {
          "dimension": "PROBLEM",
          "status": "OPEN"
        },
        {
          "dimension": "BOUNDARIES_AND_RISKS",
          "status": "OPEN"
        }
      ]
    },
    {
      "section_id": "SEC-02-PIPELINE",
      "ordinal": 2,
      "heading_path": "2. İki Aşamalı Ayrıştırma Yöntemi ve Tercihler",
      "section_sha256": "sha256:3dcf04cab6c30c471c8b02540f64a44067e0d6d7f388900a836419a935e076be",
      "in_current_batch": true,
      "has_unreadable_visuals": true,
      "unreadable_visual_note": "Akış diyagramı (pipeline_v1.png) ikili görsel olarak eklendiği için metin katmanında okunamıyor.",
      "relevant_dimensions": [
        "METHOD",
        "DECISIONS_AND_TRADEOFFS",
        "ASSUMPTIONS"
      ],
      "prior_dimension_statuses": [
        {
          "dimension": "METHOD",
          "status": "OPEN"
        },
        {
          "dimension": "DECISIONS_AND_TRADEOFFS",
          "status": "OPEN"
        },
        {
          "dimension": "ASSUMPTIONS",
          "status": "OPEN"
        }
      ]
    },
    {
      "section_id": "SEC-03-EVALUATION",
      "ordinal": 3,
      "heading_path": "3. Başarı Ölçütleri ve Doğrulama Kümesi",
      "section_sha256": "sha256:9f8e7d6c5b4a392817263544536271809f8e7d6c5b4a39281726354453627180",
      "in_current_batch": false,
      "has_unreadable_visuals": false,
      "unreadable_visual_note": null,
      "relevant_dimensions": [
        "SUCCESS_METRICS"
      ],
      "prior_dimension_statuses": [
        {
          "dimension": "SUCCESS_METRICS",
          "status": "OPEN"
        }
      ]
    }
  ],
  "current_batch_passages": [
    {
      "passage_id": "PSG-01-PROBLEM-CORE",
      "section_id": "SEC-01-PROBLEM",
      "heading_path": "1. Problem Tanımı ve Kapsam Sınırları",
      "verbatim_text": "RoleLint TR, Türkçe veri ve yazılım ilanlarındaki muğlak beceri ifadelerini normalize ederek adayın doğrulanmış kanıtlarıyla karşılaştırır. Sistem yalnız çevrimdışı indirilen ilan metinlerini işler; canlı kazıma (scraping) ve otomatik başvuru kapsam dışıdır.",
      "passage_sha256": "sha256:ea51983f5c98900e6193c9a1f985f0d0c237157176d3c2a57cf125317b534277",
      "completeness": "COMPLETE",
      "claim_epistemic_status": "PLAN",
      "evidence_basis": "USER_DECLARATION",
      "observed_evidence_refs": [],
      "cross_section_refs": [
        "SEC-03-EVALUATION"
      ]
    },
    {
      "passage_id": "PSG-02-PIPELINE-TEXT",
      "section_id": "SEC-02-PIPELINE",
      "heading_path": "2. İki Aşamalı Ayrıştırma Yöntemi ve Tercihler",
      "verbatim_text": "İlk aşamada deterministik sözlük ve regex kurallarıyla zorunlu teknoloji etiketleri çıkarılır; ikinci aşamada ise yalnız belirsiz cümleler şema kısıtlı yerel modele gönderilir. Bu sayede her ilanda tam metin model çağrısı yapılmaz.",
      "passage_sha256": "sha256:3dcf04cab6c30c471c8b02540f64a44067e0d6d7f388900a836419a935e076be",
      "completeness": "COMPLETE",
      "claim_epistemic_status": "IDEA",
      "evidence_basis": "USER_DECLARATION",
      "observed_evidence_refs": [],
      "cross_section_refs": [
        "SEC-01-PROBLEM",
        "SEC-03-EVALUATION"
      ]
    }
  ],
  "contribution_context": {
    "prepared_by_morks_from_records": true,
    "team_structure": "SOLO",
    "user_role_summary": "Tasarım ve veri şeması sahibi (bireysel proje).",
    "declared_owned_section_ids": [
      "SEC-01-PROBLEM",
      "SEC-02-PIPELINE",
      "SEC-03-EVALUATION"
    ],
    "delegated_or_teammate_section_ids": [],
    "prior_assistance_and_help_summary": "Önceki oturumda yardım kaydı yok.",
    "missing_contribution_fields": []
  },
  "session_state_snapshot": {
    "defense_session_id": "DDS-ROLELINT-20261017-01",
    "project_id": "PROJ-ROLELINT-TR",
    "session_revision": 3,
    "session_status": "ACTIVE",
    "current_document_version": "v1.0",
    "current_document_sha256": "sha256:4a8d1f7e5c3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a291",
    "delivered_question_ids": [
      "DQ-01-SCOPE_BOUNDARY",
      "DQ-02-HYBRID_TRADEOFF"
    ],
    "voided_question_ids": [],
    "disclosed_hint_ids": [],
    "taught_dimensions": [],
    "unassisted_explained_dimensions": [],
    "assisted_explained_dimensions": []
  },
  "prior_defense_batch_package": {
    "batch_exam_id": "DBATCH-20261017-001",
    "defense_session_id": "DDS-ROLELINT-20261017-01",
    "project_id": "PROJ-ROLELINT-TR",
    "document_id": "DOC-ROLELINT-ARCH-V1",
    "document_version": "v1.0",
    "document_sha256": "sha256:4a8d1f7e5c3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a291",
    "created_as_of": "2026-10-17T14:30:00+03:00",
    "registered_questions": [
      {
        "question_id": "DQ-01-SCOPE_BOUNDARY",
        "parent_question_id": null,
        "section_id": "SEC-01-PROBLEM",
        "passage_id": "PSG-01-PROBLEM-CORE",
        "target_dimension": "BOUNDARIES_AND_RISKS",
        "claim_epistemic_status": "PLAN",
        "delivered_to_learner": true,
        "voided": false,
        "defense_record_closed": false,
        "immutable_criteria": [
          {
            "criterion_id": "DCRIT-Q01-01",
            "criterion_text": "Canlı kazımanın getireceği DOM kırılganlığı, hız sınırı/erişim engeli veya hukuki/etik riskleri ayrıştırma çekirdeğinden izole etme gerekçesini açıklar.",
            "required_depth": "TRADEOFF_JUSTIFICATION"
          },
          {
            "criterion_id": "DCRIT-Q01-02",
            "criterion_text": "Çevrimdışı sabit metin girdisinin deterministik tekrar üretilebilirlik ve 3. bölümdeki değerlendirme kümesi tutarlılığı için sağladığı avantajı belirtir.",
            "required_depth": "METRIC_AND_BOUNDARY_LINK"
          }
        ]
      },
      {
        "question_id": "DQ-02-HYBRID_TRADEOFF",
        "parent_question_id": null,
        "section_id": "SEC-02-PIPELINE",
        "passage_id": "PSG-02-PIPELINE-TEXT",
        "target_dimension": "DECISIONS_AND_TRADEOFFS",
        "claim_epistemic_status": "IDEA",
        "delivered_to_learner": true,
        "voided": false,
        "defense_record_closed": false,
        "immutable_criteria": [
          {
            "criterion_id": "DCRIT-Q02-01",
            "criterion_text": "İlk aşamadaki filtreleme eşiğinin yüksek duyarlılık (recall) odaklı tutulması veya eşleşmeyen cümlelerin ikinci aşamaya devredilmesi gerekliliğini açıklar.",
            "required_depth": "FAILURE_MODE_AWARENESS"
          }
        ]
      }
    ],
    "batch_package_sha256": "0e67bc9c149af96bbf3b81a30a0f4a7d8b435e65586444a3334ea5e56d5e54c9"
  },
  "defense_responses": [
    {
      "response_id": "DRESP-20261017-01",
      "turn_id": "DTURN-20261017-01",
      "question_id": "DQ-01-SCOPE_BOUNDARY",
      "parent_question_id": null,
      "section_id": "SEC-01-PROBLEM",
      "passage_id": "PSG-01-PROBLEM-CORE",
      "target_dimension": "BOUNDARIES_AND_RISKS",
      "raw_response_text": "Canlı kazıma DOM değişimlerine ve anti-bot engellerine açık olduğu için ayrıştırıcıyı kırar; ayrıca sabit çevrimdışı metinler 3. bölümdeki doğrulama testlerini deterministik ve tekrarlanabilir kılar.",
      "is_idk_declaration": false,
      "declared_design_change": false,
      "external_verification_outcome": null,
      "criterion_ids_to_evaluate": [
        "DCRIT-Q01-01",
        "DCRIT-Q01-02"
      ]
    },
    {
      "response_id": "DRESP-20261017-02",
      "turn_id": "DTURN-20261017-02",
      "question_id": "DQ-02-HYBRID_TRADEOFF",
      "parent_question_id": null,
      "section_id": "SEC-02-PIPELINE",
      "passage_id": "PSG-02-PIPELINE-TEXT",
      "target_dimension": "DECISIONS_AND_TRADEOFFS",
      "raw_response_text": "İki aşamalı regex filtresinden vazgeçip tüm cümleleri doğrudan tek aşamalı yerel gömme (embedding) sınıflandırıcısına sokmaya karar verdim.",
      "is_idk_declaration": false,
      "declared_design_change": true,
      "external_verification_outcome": null,
      "criterion_ids_to_evaluate": [
        "DCRIT-Q02-01"
      ]
    }
  ]
}
```

### 6.4 Örnek 4 — `ANALYZE_PROJECT_DEFENSE` Çıktısı (`PROJECT_DEFENSE_ANALYZED`)

```json
{
  "schema_version": "harmanos.project_auditor.doc_defense.output.v1",
  "task_id": "DOCAUD-20261017-002",
  "as_of_evaluated": "2026-10-17T14:40:00+03:00",
  "operation_evaluated": "ANALYZE_PROJECT_DEFENSE",
  "terminal_status": "PROJECT_DEFENSE_ANALYZED",
  "error_code": null,
  "error_detail": null,
  "project_defense_scope_evaluation": {
    "project_id": "PROJ-ROLELINT-TR",
    "defense_session_id": "DDS-ROLELINT-20261017-01",
    "document_id": "DOC-ROLELINT-ARCH-V1",
    "document_version_evaluated": "v1.0",
    "document_sha256_evaluated": "sha256:4a8d1f7e5c3b2a1908f7e6d5c4b3a291807f6e5d4c3b2a1908f7e6d5c4b3a291",
    "document_type_evaluated": "ARCHITECTURE_SPEC",
    "evaluated_domain": "PYTHON_DATA_ENG",
    "allowed_assistance_level_evaluated": "QUESTION_AND_CONCEPTUAL_HINT",
    "c_or_42_detected": false,
    "prior_assistance_preserved": true,
    "batch_index_evaluated": 1,
    "total_batches_evaluated": 2,
    "inspected_section_ids_in_batch": [
      "SEC-01-PROBLEM",
      "SEC-02-PIPELINE"
    ],
    "uninspected_section_ids": [
      "SEC-03-EVALUATION"
    ],
    "waiting_visual_section_ids": [
      "SEC-02-PIPELINE"
    ],
    "missing_contribution_fields_to_ask": []
  },
  "section_dimension_matrix": [
    {
      "section_id": "SEC-01-PROBLEM",
      "dimension": "PROBLEM",
      "status": "OPEN",
      "status_reason": "AWAITING_BATCH_OR_QUESTION"
    },
    {
      "section_id": "SEC-01-PROBLEM",
      "dimension": "BOUNDARIES_AND_RISKS",
      "status": "INSPECTED",
      "status_reason": "EXPLAINED_UNASSISTED"
    },
    {
      "section_id": "SEC-02-PIPELINE",
      "dimension": "METHOD",
      "status": "OPEN",
      "status_reason": "UNREADABLE_VISUAL_WAITING"
    },
    {
      "section_id": "SEC-02-PIPELINE",
      "dimension": "DECISIONS_AND_TRADEOFFS",
      "status": "OPEN",
      "status_reason": "REQUIRES_FOLLOWUP_OR_VERIFICATION"
    },
    {
      "section_id": "SEC-02-PIPELINE",
      "dimension": "ASSUMPTIONS",
      "status": "OPEN",
      "status_reason": "AWAITING_BATCH_OR_QUESTION"
    },
    {
      "section_id": "SEC-03-EVALUATION",
      "dimension": "SUCCESS_METRICS",
      "status": "OPEN",
      "status_reason": "AWAITING_BATCH_OR_QUESTION"
    }
  ],
  "analysis_limitations": [
    {
      "limitation_code": "UNREADABLE_VISUAL_SCOPE_DEFERRED",
      "section_id": "SEC-02-PIPELINE",
      "passage_id": "PSG-02-PIPELINE-TEXT",
      "detail": "SEC-02-PIPELINE içindeki akış diyagramı okunamadığından görsele bağlı yöntem akışı doğrulaması beklemeye alındı."
    },
    {
      "limitation_code": "UNINSPECTED_BATCH_SECTIONS_REMAIN",
      "section_id": "SEC-03-EVALUATION",
      "passage_id": null,
      "detail": "SEC-03-EVALUATION sonraki bölüm grubunda (Batch 2/2) incelenmek üzere görünür tutuldu."
    }
  ],
  "learner_visible_payload": null,
  "orchestrator_only_payload": {
    "defense_questions": [],
    "defense_response_observations": [
      {
        "response_id": "DRESP-20261017-01",
        "turn_id": "DTURN-20261017-01",
        "question_id": "DQ-01-SCOPE_BOUNDARY",
        "parent_question_id": null,
        "section_id": "SEC-01-PROBLEM",
        "passage_id": "PSG-01-PROBLEM-CORE",
        "target_dimension": "BOUNDARIES_AND_RISKS",
        "evaluation_verdict": "DIRECT_CRITERION_MATCH",
        "assistance_classification_for_response": "UNASSISTED",
        "criterion_evaluations": [
          {
            "criterion_id": "DCRIT-Q01-01",
            "criterion_text": "Canlı kazımanın getireceği DOM kırılganlığı, hız sınırı/erişim engeli veya hukuki/etik riskleri ayrıştırma çekirdeğinden izole etme gerekçesini açıklar.",
            "status": "DEMONSTRATED",
            "verbatim_response_excerpt": "Canlı kazıma DOM değişimlerine ve anti-bot engellerine açık olduğu için ayrıştırıcıyı kırar",
            "observation_note": "Kısa ve doğrudan yanıt, canlı kazıma kırılganlığını ve izolasyon gerekçesini tam karşılıyor."
          },
          {
            "criterion_id": "DCRIT-Q01-02",
            "criterion_text": "Çevrimdışı sabit metin girdisinin deterministik tekrar üretilebilirlik ve 3. bölümdeki değerlendirme kümesi tutarlılığı için sağladığı avantajı belirtir.",
            "status": "DEMONSTRATED",
            "verbatim_response_excerpt": "sabit çevrimdışı metinler 3. bölümdeki doğrulama testlerini deterministik ve tekrarlanabilir kılar",
            "observation_note": "3. bölümdeki doğrulama kümesiyle deterministik tekrar üretilebilirlik bağı açıkça kuruldu."
          }
        ],
        "followup_question": null,
        "external_verification_request": null,
        "teaching_transition_packet": null
      },
      {
        "response_id": "DRESP-20261017-02",
        "turn_id": "DTURN-20261017-02",
        "question_id": "DQ-02-HYBRID_TRADEOFF",
        "parent_question_id": null,
        "section_id": "SEC-02-PIPELINE",
        "passage_id": "PSG-02-PIPELINE-TEXT",
        "target_dimension": "DECISIONS_AND_TRADEOFFS",
        "evaluation_verdict": "DESIGN_CHANGED_WITHOUT_RATIONALE",
        "assistance_classification_for_response": "NOT_EXPLAINED",
        "criterion_evaluations": [
          {
            "criterion_id": "DCRIT-Q02-01",
            "criterion_text": "İlk aşamadaki filtreleme eşiğinin yüksek duyarlılık (recall) odaklı tutulması veya eşleşmeyen cümlelerin ikinci aşamaya devredilmesi gerekliliğini açıklar.",
            "status": "PARTIAL_OR_VAGUE",
            "verbatim_response_excerpt": "İki aşamalı regex filtresinden vazgeçip tüm cümleleri doğrudan tek aşamalı yerel gömme (embedding) sınıflandırıcısına sokmaya karar verdim.",
            "observation_note": "Kullanıcı belgedeki iki aşamalı tasarım kararını değiştirdiğini belirtti ancak bu değişikliğin teknik gerekçesini ve ödünleşimini açıklamadı."
          }
        ],
        "followup_question": {
          "followup_question_id": "FQ-DQ-02-HYBRID_TRADEOFF-01",
          "parent_question_id": "DQ-02-HYBRID_TRADEOFF",
          "section_id": "SEC-02-PIPELINE",
          "passage_id": "PSG-02-PIPELINE-TEXT",
          "target_dimension": "DECISIONS_AND_TRADEOFFS",
          "followup_reason": "DESIGN_DECISION_CHANGE_RATIONALE",
          "neutral_followup_prompt": "Belgedeki iki aşamalı sözlük/regex + model kurgusundan tek aşamalı gömme (embedding) sınıflandırıcısına geçiş kararınızın temel gerekçesi nedir ve bu değişikliğin kesinlik (precision) ile hesaplama maliyeti üzerindeki ödünleşimini nasıl değerlendirdiniz?"
        },
        "external_verification_request": null,
        "teaching_transition_packet": null
      }
    ],
    "defense_outcome_summary": {
      "unassisted_explained_dimensions": [
        {
          "section_id": "SEC-01-PROBLEM",
          "dimension": "BOUNDARIES_AND_RISKS"
        }
      ],
      "assisted_explained_dimensions": [],
      "open_dimensions": [
        {
          "section_id": "SEC-01-PROBLEM",
          "dimension": "PROBLEM",
          "open_reason": "Henüz yanıtlanmadı."
        },
        {
          "section_id": "SEC-02-PIPELINE",
          "dimension": "METHOD",
          "open_reason": "Görsel diyagram okunamadığı için beklemeye alındı."
        },
        {
          "section_id": "SEC-02-PIPELINE",
          "dimension": "DECISIONS_AND_TRADEOFFS",
          "open_reason": "Tasarım değişikliği gerekçesi için nötr takip sorusu yöneltildi."
        },
        {
          "section_id": "SEC-02-PIPELINE",
          "dimension": "ASSUMPTIONS",
          "open_reason": "Henüz yanıtlanmadı."
        },
        {
          "section_id": "SEC-03-EVALUATION",
          "dimension": "SUCCESS_METRICS",
          "open_reason": "Sonraki bölüm grubunda (Batch 2/2) incelenecek."
        }
      ],
      "governance_locks": {
        "overall_score_generated": false,
        "independent_competency_granted": false,
        "project_gate_approval_granted": false,
        "eligible_for_independent_attempt_submission": false
      }
    }
  }
}
```
