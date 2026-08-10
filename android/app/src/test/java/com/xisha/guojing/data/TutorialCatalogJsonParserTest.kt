package com.xisha.guojing.data

import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class TutorialCatalogJsonParserTest {
    private val parser = TutorialCatalogJsonParser()

    @Test
    fun parses_backend_summary_contract() {
        val tutorials = parser.parse(
            """
            [
              {
                "graph_id": "wechat-call",
                "title": "微信打电话",
                "package_name": "com.tencent.mm",
                "recorded_version_name": "8.0.60",
                "recorded_version_code": 2800,
                "revision_number": 3,
                "published_at": "2026-08-09T07:00:00Z"
              }
            ]
            """.trimIndent(),
        )

        assertEquals(1, tutorials.size)
        assertEquals("wechat-call", tutorials.single().graphId)
        assertEquals("微信打电话", tutorials.single().title)
        assertEquals(2800, tutorials.single().recordedVersionCode)
        assertEquals(3, tutorials.single().revisionNumber)
    }

    @Test
    fun rejects_non_array_root() {
        assertThrows(TutorialCatalogFormatException::class.java) {
            parser.parse("{\"tutorials\": []}")
        }
    }

    @Test
    fun rejects_missing_required_field() {
        val error = assertThrows(TutorialCatalogFormatException::class.java) {
            parser.parse(
                """
                [{
                  "graph_id": "wechat-call",
                  "title": "",
                  "package_name": "com.tencent.mm",
                  "recorded_version_name": "8.0.60",
                  "recorded_version_code": 2800,
                  "revision_number": 3,
                  "published_at": "2026-08-09T07:00:00Z"
                }]
                """.trimIndent(),
            )
        }

        assertEquals("Tutorial at index 0 has no non-empty 'title'", error.message)
    }

    @Test
    fun rejects_null_required_string() {
        assertThrows(TutorialCatalogFormatException::class.java) {
            parser.parse(
                """
                [{
                  "graph_id": null,
                  "title": "微信打电话",
                  "package_name": "com.tencent.mm",
                  "recorded_version_name": "8.0.60",
                  "recorded_version_code": 2800,
                  "revision_number": 3,
                  "published_at": "2026-08-09T07:00:00Z"
                }]
                """.trimIndent(),
            )
        }
    }
}
