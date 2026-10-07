package com.aismartclass

import org.json.JSONArray
import org.json.JSONObject
import java.io.ByteArrayOutputStream
import java.io.DataOutputStream
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

private class SmartclassHttpException(message: String) : IOException(message)

internal class SmartclassApi(baseUrl: String, private val token: String? = null) {
    private val baseUrl = baseUrl.trim().trimEnd('/')

    fun login(username: String, password: String): JSONObject = requestJson(
        "/api/login",
        "POST",
        JSONObject().put("username", username).put("password", password)
    )

    fun tests(classId: String): JSONArray = requestArray("/api/classes/$classId/tests")

    fun plans(classId: String): JSONArray = requestArray("/api/classes/$classId/plans")

    fun submissions(classId: String, isTeacher: Boolean): JSONArray = requestArray(
        if (isTeacher) "/api/classes/$classId/submissions" else "/api/students/me/submissions"
    )

    fun createTest(classId: String, title: String, subject: String, kind: String, dueDate: String): JSONObject =
        requestJson("/api/tests", "POST", JSONObject()
            .put("class_id", classId)
            .put("title", title)
            .put("subject", subject)
            .put("kind", kind)
            .put("due_date", dueDate))

    fun uploadTestPaper(testId: String, filename: String, bytes: ByteArray) =
        requestMultipart("/api/tests/$testId/paper", "paper", filename, bytes)

    fun createPlan(classId: String, week: String, title: String, target: String): JSONObject =
        requestJson("/api/classes/$classId/plans", "POST", JSONObject()
            .put("week", week).put("title", title).put("target", target))

    fun uploadAnswerSheet(testId: String, filename: String, bytes: ByteArray): JSONObject =
        requestMultipart("/api/tests/$testId/submissions", "answer_sheet", filename, bytes)

    fun evaluate(submissionId: String): JSONObject = requestJson("/api/submissions/$submissionId/evaluate", "POST", JSONObject())

    fun download(path: String): ByteArray = requestBytes(path, "GET", null, null)

    private fun requestArray(path: String): JSONArray = JSONArray(String(requestBytes(path, "GET", null, null), Charsets.UTF_8))

    private fun requestJson(path: String, method: String, body: JSONObject): JSONObject =
        JSONObject(String(requestBytes(path, method, body.toString().toByteArray(Charsets.UTF_8), "application/json"), Charsets.UTF_8))

    private fun requestMultipart(path: String, partName: String, filename: String, fileBytes: ByteArray): JSONObject {
        val boundary = "Smartclass-${System.nanoTime()}"
        val body = ByteArrayOutputStream()
        val safeFilename = filename.replace("\"", "")
        DataOutputStream(body).use { stream ->
            stream.writeBytes("--$boundary\r\n")
            stream.writeBytes("Content-Disposition: form-data; name=\"$partName\"; filename=\"$safeFilename\"\r\n")
            stream.writeBytes("Content-Type: application/pdf\r\n\r\n")
            stream.write(fileBytes)
            stream.writeBytes("\r\n--$boundary--\r\n")
        }
        return JSONObject(String(requestBytes(path, "POST", body.toByteArray(), "multipart/form-data; boundary=$boundary"), Charsets.UTF_8))
    }

    private fun requestBytes(path: String, method: String, body: ByteArray?, contentType: String?): ByteArray {
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 12_000
            readTimeout = 180_000
            setRequestProperty("Accept", "application/json, application/pdf")
            if (token != null) setRequestProperty("Authorization", "Bearer $token")
            if (contentType != null) setRequestProperty("Content-Type", contentType)
            doInput = true
        }
        try {
            if (body != null) {
                connection.doOutput = true
                connection.outputStream.use { it.write(body) }
            }
            val status = connection.responseCode
            val response = if (status in 200..299) connection.inputStream.use { it.readBytes() }
                else connection.errorStream?.use { it.readBytes() } ?: ByteArray(0)
            if (status !in 200..299) {
                val message = runCatching { JSONObject(String(response, Charsets.UTF_8)).optString("detail") }.getOrNull()
                throw SmartclassHttpException(message?.takeIf { it.isNotBlank() } ?: "Server returned HTTP $status")
            }
            return response
        } catch (exception: SmartclassHttpException) {
            throw exception
        } catch (exception: IOException) {
            throw IOException("Could not reach $baseUrl. Check that the backend is running and the phone can reach this address.", exception)
        } finally {
            connection.disconnect()
        }
    }
}
