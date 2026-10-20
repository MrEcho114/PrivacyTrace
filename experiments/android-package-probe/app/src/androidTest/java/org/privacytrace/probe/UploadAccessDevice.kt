package org.privacytrace.probe

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import java.util.zip.ZipInputStream

internal fun verifyUploadAccess(context: Context) {
    val sessions = AndroidUploadSessions(context)
    val origin = "https://synthetic-upload.invalid/"
    val other = "https://other-synthetic-upload.invalid/"
    val instance = "12345678-1234-4234-8234-123456789abc"
    val saved = UploadSession(origin, instance, "a".repeat(32), "pt_cap_" + "synthetic".repeat(4), "f".repeat(64))
    try {
        sessions.forget(origin)
        check(sessions.load(origin, instance) == null)
        try {
            sessions.save(saved) { true }
            error("cancelled save")
        } catch (error: ServerProbeException) { check(error.code == "CANCELLED") }
        check(sessions.load(origin, instance) == null)
        sessions.save(saved)
        check(AndroidUploadSessions(context).load(origin, instance) == saved)
        check(sessions.load(other, instance) == null)
        try {
            sessions.load(origin, "22345678-1234-4234-8234-123456789abc")
            error("instance changed")
        } catch (error: ServerProbeException) { check(error.code == "INSTANCE_MISMATCH") }
        val stored = context.noBackupFilesDir.listFiles()!!.filter { it.name.startsWith("upload-") }
        check(stored.isNotEmpty())
        check(stored.none { String(it.readBytes(), Charsets.ISO_8859_1).contains(saved.token) })
        sessions.clear(origin, instance)
        check(sessions.load(origin, instance) == null)
        sessions.save(saved)
        sessions.forget(origin)
        check(sessions.load(origin, instance) == null)
    } finally { sessions.forget(origin) }
}

internal fun verifyInstalledUpload(context: Context, expectedBase: String, expectedSplit: String) {
    val source = AndroidPackageSource(context.packageManager)
    val confirmed = PackageProbe(source).prepare("org.privacytrace.probe.fixture")
    check(confirmed.parts.size == 2)
    val instance = "12345678-1234-4234-8234-123456789abc"
    val caps = UploadCapabilities(instance, 157286400, 157286400, 157286400, 101)
    UploadArchive.prepare(context.cacheDir, source, confirmed, caps) { false }.use { archive ->
        check(archive.result.parts.single { it.splitName == null }.sha256 == expectedBase)
        check(archive.result.parts.single { it.splitName == "fixture_feature" }.sha256 == expectedSplit)
        HealthTlsFixture().use { fixture ->
            val draft = "d".repeat(32)
            val token = "pt_cap_" + "synthetic".repeat(4)
            var saved: UploadSession? = null
            val sessions = object : UploadSessions {
                override fun load(origin: String, instance: String) = saved
                override fun save(session: UploadSession, cancelled: () -> Boolean) {
                    check(!cancelled()); saved = session
                }
                override fun clear(origin: String, instance: String) { saved = null }
            }
            val capability = """{"protocol":"privacytrace-mobile/1","supported":true,"instance_id":"$instance","upload_format":"apk-or-zip","max_upload_bytes":157286400,"max_file_bytes":157286400,"max_total_bytes":157286400,"max_files":101,"retention":"UNTIL_EXPLICIT_DELETE","delete_draft":true}"""
            val partValues = archive.result.parts.map { part -> JSONObject()
                .put("package_name", archive.result.packageName).put("version_code", confirmed.versionCode)
                .put("part", if (part.splitName == null) "BASE" else "SPLIT")
                .put("split_name", part.splitName ?: JSONObject.NULL)
                .put("sha256", part.sha256).put("size_bytes", part.bytes) }
            val receipt = JSONObject().put("id", draft).put("uploaded", true)
                .put("package_set", JSONObject().put("package_name", archive.result.packageName)
                    .put("version_code", confirmed.versionCode).put("base", partValues[0])
                    .put("splits", JSONArray().put(partValues[1])).put("total_size_bytes", archive.result.totalBytes)).toString()
            fixture.server.enqueue(fixture.json(capability))
            fixture.server.enqueue(fixture.json("""{"id":"$draft","capability_token":"$token"}"""))
            fixture.server.enqueue(fixture.json(receipt)); fixture.server.enqueue(fixture.json(receipt))
            check(AnalysisTransport(fixture.origin, sessions, fixture.client).upload(archive, caps).state == "SERVER_CONFIRMED")
            val requests = (1..4).map { checkNotNull(fixture.server.takeRequest(3, TimeUnit.SECONDS)) }
            check(requests.take(2).all { it.getHeader("Authorization") == null })
            check(requests[2].getHeader("Authorization") == "Bearer $token")
            ZipInputStream(requests[2].body.inputStream()).use { zip ->
                archive.result.parts.forEachIndexed { index, part ->
                    check(zip.nextEntry.name == if (index == 0) "base.apk" else "part-$index.apk")
                    val digest = MessageDigest.getInstance("SHA-256").digest(zip.readBytes())
                        .joinToString("") { "%02x".format(it) }
                    check(digest == part.sha256)
                }
                check(zip.nextEntry == null)
            }
        }
    }
}
