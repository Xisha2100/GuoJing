package com.xisha.guojing.data

import com.xisha.guojing.model.AgentProtocolException
import com.xisha.guojing.model.GuidanceStatus
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

class AgentProtocolTest {
    @Test
    fun parses_completed_run_with_one_valid_target() {
        val result = AgentProtocol.parseRun(
            """{"schema_version":"1.0","run_id":"11111111-1111-1111-1111-111111111111","session_id":"22222222-2222-2222-2222-222222222222","status":"completed","result":{"status":"continue","instruction":"点击右上角加号","target":{"left":0.8,"top":0.02,"right":0.98,"bottom":0.12},"confidence":0.93},"error_code":null,"retryable":false}""",
        )

        assertEquals(GuidanceStatus.Continue, result.result?.status)
        assertEquals(0.8, result.result?.target?.left ?: 0.0, 0.0001)
    }

    @Test
    fun rejects_unknown_fields_and_schema_versions() {
        val response = """{"schema_version":"2.0","session_id":"11111111-1111-1111-1111-111111111111","access_token":"secret","status":"active","extra":true}"""

        assertThrows(AgentProtocolException::class.java) {
            AgentProtocol.parseSession(response)
        }
    }

    @Test
    fun rejects_low_confidence_continue_result() {
        val response = """{"schema_version":"1.0","run_id":"11111111-1111-1111-1111-111111111111","session_id":"22222222-2222-2222-2222-222222222222","status":"completed","result":{"status":"continue","instruction":"点击按钮","target":{"left":0.1,"top":0.1,"right":0.2,"bottom":0.2},"confidence":0.69},"error_code":null,"retryable":false}"""

        assertThrows(AgentProtocolException::class.java) {
            AgentProtocol.parseRun(response)
        }
    }

    @Test
    fun rejects_target_for_completed_decision() {
        val response = """{"schema_version":"1.0","run_id":"11111111-1111-1111-1111-111111111111","session_id":"22222222-2222-2222-2222-222222222222","status":"completed","result":{"status":"completed","instruction":"完成","target":{"left":0.1,"top":0.1,"right":0.2,"bottom":0.2},"confidence":0.9},"error_code":null,"retryable":false}"""

        assertThrows(AgentProtocolException::class.java) {
            AgentProtocol.parseRun(response)
        }
    }

    @Test
    fun rejects_string_in_place_of_boolean() {
        val response = """{"schema_version":"1.0","run_id":"11111111-1111-1111-1111-111111111111","session_id":"22222222-2222-2222-2222-222222222222","status":"failed","result":null,"error_code":"agent_timeout","retryable":"true"}"""

        assertThrows(AgentProtocolException::class.java) {
            AgentProtocol.parseRun(response)
        }
    }
}
