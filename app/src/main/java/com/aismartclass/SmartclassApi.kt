package com.aismartclass

import org.json.JSONArray
import org.json.JSONException
import org.json.JSONObject
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

private class SmartclassHttpException(message: String) : IOException(message)

internal class SmartclassApi(baseUrl: String, private val token: String? = null) {
    private val baseUrl = baseUrl.trim().trimEnd('/').let { address ->
        if (address.startsWith("http://") || address.startsWith("https://")) address else "http://$address"
    }

    fun health(): JSONObject = JSONObject(String(requestBytes("/api/health", "GET", null, null), Charsets.UTF_8))

    fun login(username: String, password: String): JSONObject = requestJson(
        "/api/login",
        "POST",
        JSONObject().put("username", username).put("password", password)
    )

    fun tests(classId: String): JSONArray = requestArray("/api/classes/$classId/tests")

    fun digitalTest(testId: String): JSONObject = requestJson("/api/tests/$testId", "GET", null)

    fun myAnalyses(): JSONArray = requestArray("/api/students/me/analyses")

    fun attemptReview(testId: String, studentId: String? = null): JSONObject {
        val query = studentId?.let { "?student_id=${java.net.URLEncoder.encode(it, "UTF-8")}" } ?: ""
        return requestJson("/api/tests/$testId/attempts$query", "GET", null)
    }

    fun studentAnalysis(classId: String, studentId: String, asOf: String? = null, subject: String? = null): JSONObject {
        val query = listOfNotNull(
            asOf?.let { "as_of=${java.net.URLEncoder.encode(it, "UTF-8")}" },
            subject?.let { "subject=${java.net.URLEncoder.encode(it, "UTF-8")}" }
        ).joinToString("&")
        return requestJson("/api/classes/$classId/students/$studentId/analysis" + if (query.isBlank()) "" else "?$query", "GET", null)
    }

    fun classRatings(classId: String): JSONArray = requestArray("/api/classes/$classId/ratings")

    fun metrics(classId: String, subject: String): JSONArray = requestArray(
        "/api/classes/$classId/metrics?subject=${java.net.URLEncoder.encode(subject, "UTF-8")}"
    )

    fun plans(classId: String): JSONArray = requestArray("/api/classes/$classId/plans")

    fun createDigitalTest(classId: String, title: String, subject: String, kind: String, dueDate: String, isMock: Boolean, durationMinutes: Int): JSONObject =
        requestJson("/api/tests", "POST", JSONObject()
            .put("class_id", classId)
            .put("title", title)
            .put("subject", subject)
            .put("kind", kind)
            .put("due_date", dueDate)
            .put("is_mock", isMock)
            .put("duration_minutes", durationMinutes))

    fun replaceDigitalTest(testId: String, body: JSONObject): JSONObject =
        requestJson("/api/tests/$testId", "PUT", body)

    fun deleteDigitalTest(testId: String): JSONObject =
        requestJson("/api/tests/$testId", "DELETE", JSONObject())

    fun addQuestion(testId: String, question: JSONObject): JSONObject =
        requestJson("/api/tests/$testId/questions", "POST", question)

    fun publishTest(testId: String): JSONObject = requestJson("/api/tests/$testId/publish", "POST", JSONObject())

    fun submitTest(testId: String, answers: JSONObject, isMock: Boolean): JSONObject =
        requestJson("/api/tests/$testId/attempts", "POST", JSONObject().put("answers", answers).put("is_mock", isMock))

    fun createPlan(classId: String, week: String, title: String, target: String): JSONObject =
        requestJson("/api/classes/$classId/plans", "POST", JSONObject()
            .put("week", week).put("title", title).put("target", target))

    fun createMetric(classId: String, subject: String, name: String, description: String, weight: Double): JSONObject =
        requestJson("/api/classes/$classId/metrics", "POST", JSONObject()
            .put("subject", subject).put("name", name).put("description", description).put("weight", weight))

    fun adminClasses(): JSONArray = requestArray("/api/admin/classes")

    fun adminCreateClass(name: String, year: String): JSONObject =
        requestJson("/api/admin/classes", "POST", JSONObject().put("name", name).put("year", year))

    fun adminUsers(role: String? = null): JSONArray = requestArray("/api/admin/users" + (role?.let { "?role=$it" } ?: ""))

    fun adminCreateStudent(username: String, name: String, password: String, classId: String): JSONObject =
        requestJson("/api/admin/students", "POST", JSONObject().put("username", username).put("name", name).put("password", password).put("class_id", classId))

    fun adminCreateTeacher(username: String, name: String, password: String, assignments: JSONArray): JSONObject =
        requestJson("/api/admin/teachers", "POST", JSONObject().put("username", username).put("name", name).put("password", password).put("assignments", assignments))

    fun adminUpdateUser(userId: String, updates: JSONObject): JSONObject =
        requestJson("/api/admin/users/$userId", "PATCH", updates)

    fun adminDeleteUser(userId: String): JSONObject =
        requestJson("/api/admin/users/$userId", "DELETE", JSONObject())

    fun adminSetTeacherAssignments(userId: String, assignments: JSONArray): JSONObject =
        requestJson("/api/admin/teachers/$userId/assignments", "PUT", JSONObject().put("assignments", assignments))

    fun adminAssignTeacher(teacherId: String, classId: String, assignmentType: String, subject: String?): JSONObject =
        requestJson("/api/admin/assignments", "POST", JSONObject().put("teacher_id", teacherId).put("class_id", classId).put("assignment_type", assignmentType).put("subject", subject))

    fun adminSetActive(userId: String, active: Boolean): JSONObject =
        requestJson("/api/admin/users/$userId/active?active=$active", "PATCH", JSONObject())

    private fun requestArray(path: String): JSONArray = try {
        JSONArray(String(requestBytes(path, "GET", null, null), Charsets.UTF_8))
    } catch (failure: JSONException) {
        throw IOException("The server returned an invalid response. Please try again.", failure)
    }

    private fun requestJson(path: String, method: String, body: JSONObject?): JSONObject =
        try {
            JSONObject(String(requestBytes(path, method, body?.toString()?.toByteArray(Charsets.UTF_8), if (body == null) null else "application/json"), Charsets.UTF_8))
        } catch (failure: JSONException) {
            throw IOException("The server returned an invalid response. Please try again.", failure)
        }

    private fun requestBytes(path: String, method: String, body: ByteArray?, contentType: String?): ByteArray {
        val connection = (URL("$baseUrl$path").openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 12_000
            readTimeout = 180_000
            setRequestProperty("Accept", "application/json")
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
