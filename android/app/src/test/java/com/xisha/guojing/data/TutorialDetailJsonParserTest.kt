package com.xisha.guojing.data

import com.xisha.guojing.model.PrivacyMode
import com.xisha.guojing.model.RiskLevel
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class TutorialDetailJsonParserTest {
    private val parser = TutorialDetailJsonParser()

    @Test
    fun parses_published_tutorial_graph_contract() {
        val detail = parser.parse(VALID_TUTORIAL_DETAIL_JSON)

        assertEquals(3, detail.revisionNumber)
        assertEquals("wechat_open_family_chat", detail.graph.graphId)
        assertEquals("chat_list", detail.graph.startNodeId)
        assertEquals(2, detail.graph.nodes.size)
        assertEquals(PrivacyMode.LocalOnly, detail.graph.nodes.first().privacyMode)
        assertEquals("家人", detail.graph.nodes.first().anchors.single().locator.text)
        assertEquals(RiskLevel.Low, detail.graph.transitions.single().riskLevel)
    }

    @Test
    fun rejects_unsupported_schema_version() {
        val error = assertThrows(TutorialDetailFormatException::class.java) {
            parser.parse(
                VALID_TUTORIAL_DETAIL_JSON.replace(
                    "\"schema_version\": \"1.0\"",
                    "\"schema_version\": \"2.0\"",
                ),
            )
        }

        assertEquals("Unsupported tutorial schema version '2.0'", error.message)
    }

    @Test
    fun rejects_graph_with_missing_start_node() {
        val error = assertThrows(TutorialDetailFormatException::class.java) {
            parser.parse(
                VALID_TUTORIAL_DETAIL_JSON.replace(
                    "\"start_node_id\": \"chat_list\"",
                    "\"start_node_id\": \"missing\"",
                ),
            )
        }

        assertEquals("Tutorial graph start node does not exist", error.message)
    }

    @Test
    fun rejects_unknown_risk_level() {
        assertThrows(TutorialDetailFormatException::class.java) {
            parser.parse(
                VALID_TUTORIAL_DETAIL_JSON.replace(
                    "\"risk_level\": \"low\"",
                    "\"risk_level\": \"unknown\"",
                ),
            )
        }
    }

    @Test
    fun rejects_null_required_graph_id() {
        assertThrows(TutorialDetailFormatException::class.java) {
            parser.parse(
                VALID_TUTORIAL_DETAIL_JSON.replace(
                    "\"graph_id\": \"wechat_open_family_chat\"",
                    "\"graph_id\": null",
                ),
            )
        }
    }

}

internal val VALID_TUTORIAL_DETAIL_JSON =
    """
            {
              "revision_number": 3,
              "published_at": "2026-08-09T07:00:00Z",
              "graph": {
                "schema_version": "1.0",
                "graph_id": "wechat_open_family_chat",
                "title": "打开家人微信聊天",
                "recorded_app": {
                  "package_name": "com.tencent.mm",
                  "version_name": "8.0.60",
                  "version_code": 2600
                },
                "start_node_id": "chat_list",
                "nodes": [
                  {
                    "node_id": "chat_list",
                    "title": "微信聊天列表",
                    "anchors": [
                      {
                        "anchor_id": "family_chat",
                        "role": "required",
                        "locator": {
                          "resource_id": null,
                          "content_description": null,
                          "text": "家人",
                          "ocr_text": null
                        },
                        "relative_constraints": [],
                        "bounds_fallback": null
                      }
                    ],
                    "privacy_mode": "local_only",
                    "verification_status": "verified",
                    "last_verified_version_code": 2600
                  },
                  {
                    "node_id": "conversation",
                    "title": "家人聊天页",
                    "anchors": [
                      {
                        "anchor_id": "chat_title",
                        "role": "required",
                        "locator": {
                          "resource_id": null,
                          "content_description": null,
                          "text": "家人",
                          "ocr_text": null
                        },
                        "relative_constraints": [],
                        "bounds_fallback": null
                      }
                    ],
                    "privacy_mode": "local_only",
                    "verification_status": "verified",
                    "last_verified_version_code": 2600
                  }
                ],
                "transitions": [
                  {
                    "transition_id": "open_family_chat",
                    "source_node_id": "chat_list",
                    "target_node_id": "conversation",
                    "action_kind": "tap",
                    "instruction": "点击“家人”聊天",
                    "risk_level": "low",
                    "target_anchor_id": "family_chat"
                  }
                ]
              }
            }
    """.trimIndent()
