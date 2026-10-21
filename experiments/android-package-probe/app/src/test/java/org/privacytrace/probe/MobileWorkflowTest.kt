package org.privacytrace.probe

import javax.crypto.spec.SecretKeySpec
import org.junit.Assert.*
import org.junit.Test

class MobileWorkflowTest {
    @Test fun nativePolicyStartAndReportUseOnlyTheSelectedDraftCapability() {
        HealthTlsFixture().use { fixture ->
            val id = "a".repeat(32)
            val job = "b".repeat(32)
            val token = "pt_cap_" + "synthetic".repeat(4)
            val instance = "12345678-1234-4234-8234-123456789abc"
            val part = PartDigest(null, 12, "c".repeat(64))
            val fingerprint = receiptFingerprint("org.example.fixture", 1, listOf(part))
            val session = UploadSession(fixture.origin, instance, id, token, fingerprint)
            val sessions = object : UploadSessions {
                override fun load(origin: String, instance: String): UploadSession {
                    check(origin == session.origin && instance == session.instance); return session
                }
                override fun save(session: UploadSession, cancelled: () -> Boolean) = error("not needed")
                override fun clear(origin: String, instance: String) = error("not needed")
            }
            val caps = """{"protocol":"privacytrace-mobile/1","supported":true,"instance_id":"$instance","upload_format":"apk-or-zip","max_upload_bytes":157286400,"max_file_bytes":157286400,"max_total_bytes":157286400,"max_files":101,"retention":"UNTIL_EXPLICIT_DELETE","delete_draft":true}"""
            val draft = """{"id":"$id","revision":1,"uploaded":true,"sources":[],"jobs":[{"job_id":"$job"}],"package_set":{"package_name":"org.example.fixture","version_code":1,"total_size_bytes":12,"base":{"package_name":"org.example.fixture","version_code":1,"part":"BASE","split_name":null,"size_bytes":12,"sha256":"${part.sha256}"},"splits":[]}}"""
            val transport = AnalysisTransport(fixture.origin, sessions, fixture.client)
            for ((action, payload, path, result) in listOf(
                listOf("import", "{\"source\":{\"id\":\"policy\",\"title\":\"Policy\",\"text\":\"原句\",\"source_type\":\"SDK_POLICY\"}}", "/api/v1/web/drafts/$id/import-external", "{\"revision\":2}"),
                listOf("start", "{\"revision\":1,\"request_id\":\"${"d".repeat(32)}\"}", "/api/v1/web/drafts/$id/start", "{\"id\":\"$job\",\"state\":\"QUEUED\"}"),
                listOf("report", "{}", "/api/v1/jobs/$job/report", "{\"demo\":false,\"token\":\"$token\",\"result\":{\"issues\":[]}}"),
            )) {
                fixture.server.enqueue(fixture.json(caps)); fixture.server.enqueue(fixture.json(draft)); fixture.server.enqueue(fixture.json(result))
                val response = transport.workflow(action, payload)
                assertEquals(id, response["draft"])
                assertFalse(response.toString().contains(token))
                assertNull(fixture.server.takeRequest().getHeader("Authorization"))
                assertEquals("Bearer $token", fixture.server.takeRequest().getHeader("Authorization"))
                val sent = fixture.server.takeRequest()
                assertEquals(path, sent.path)
                assertEquals("Bearer $token", sent.getHeader("Authorization"))
                assertFalse(sent.body.readUtf8().contains("personal-model-key"))
            }
        }
    }

    @Test fun personalModelReceivesOnlyThePromptAndItsOwnKey() {
        HealthTlsFixture().use { model ->
            HealthTlsFixture().use { analysis ->
                val files = object : ModelConfigFiles {
                    var record: ByteArray? = null
                    override fun read() = record
                    override fun write(record: ByteArray) { this.record = record }
                    override fun delete() { record = null }
                }
                val keys = object : ModelConfigKeys {
                    override fun key(create: Boolean) = SecretKeySpec(ByteArray(32) { 7 }, "AES")
                    override fun delete() {}
                }
                val configuration = ModelConfiguration(files, keys)
                configuration.commitSave(configuration.prepareSave(model.origin + "v1/chat/completions", "personal-model-key".toCharArray()))
                val result = "{\"version\":\"privacytrace-policy-collector/1\",\"results\":[{\"state\":\"OFFLINE\",\"source\":null}]}"
                model.server.enqueue(model.json("{\"choices\":[{\"finish_reason\":\"stop\",\"message\":{\"content\":${TransportJson.quote(result)}}}],\"usage\":{\"cost\":0.01}}"))
                val text = ModelPolicyCall(configuration, analysis.origin, model.client).collect("compatible-chat", "Find policy for org.example.fixture")
                assertEquals(result, text)
                val sent = model.server.takeRequest()
                assertEquals("/v1/chat/completions", sent.path)
                assertEquals("Bearer personal-model-key", sent.getHeader("Authorization"))
                assertTrue(sent.body.readUtf8().contains("org.example.fixture"))
                assertEquals(0, analysis.server.requestCount)
            }
        }
    }
}
