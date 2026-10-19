package com.aismartclass

import android.app.DatePickerDialog
import android.content.Context
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowDropDown
import androidx.compose.material.icons.filled.AssignmentTurnedIn
import androidx.compose.material.icons.filled.Person
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material.icons.filled.ShowChart
import androidx.compose.material.icons.filled.BarChart
import androidx.compose.material.icons.filled.Lock
import androidx.compose.material.icons.filled.PersonOutline
import androidx.compose.material.icons.filled.School
import androidx.compose.material.icons.filled.TipsAndUpdates
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material.icons.filled.Home
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateMapOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.draw.clip
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONArray
import org.json.JSONObject
import kotlinx.coroutines.delay
import java.util.Calendar
import java.util.concurrent.Executors

private const val ClassroomLog = "AIClassroom"
private val Ink = Color(0xFF10242E)
private val Muted = Color(0xFF5E7381)
private val Paper = Color(0xFFF5F7FB)
private val Green = Color(0xFFBFE7D7)
private val Teal = Color(0xFF145C56)
private val Coral = Color(0xFFE8846B)
private val Accent = Color(0xFF2B7A78)
private val Panel = Color(0xFFFFFFFF)

private data class SchoolClass(val id: String, val name: String, val year: String, val isClassTeacher: Boolean = false, val subjects: List<String> = emptyList())
private data class SignedInUser(val id: String, val name: String, val username: String, val role: String, val isAdmin: Boolean, val token: String, val classes: List<SchoolClass>)
private data class DigitalTest(val id: String, val title: String, val subject: String, val kind: String, val dueDate: String, val questionCount: Int, val isMock: Boolean, val completed: Boolean, val pending: Boolean, val durationMinutes: Int = 60, val studentsTaken: Int = 0)
private data class DigitalQuestion(val id: String, val prompt: String, val points: Double, val type: String, val options: List<String>)
private data class TestAnalysis(val testId: String, val title: String, val subject: String, val date: String, val score: String, val maxScore: String, val rating: String, val analysis: String, val advice: String, val strengths: List<String>, val focus: List<String>)
private data class StudentRating(val id: String, val name: String, val overall: String?, val overallAnalysis: String?, val subjects: JSONObject, val metrics: JSONObject, val asOf: String?)
private data class DraftQuestion(val prompt: String, val points: Double, val type: String, val options: List<String>, val answerKey: Any)

class ClassroomActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { SmartclassRoot(this) }
    }
}

@Composable
private fun SmartclassRoot(context: Context) {
    val activity = context as ComponentActivity
    val executor = remember { Executors.newSingleThreadExecutor() }
    val backendUrl = BuildConfig.DEFAULT_BACKEND_URL
    var user by remember { mutableStateOf<SignedInUser?>(null) }
    var selectedClassId by remember { mutableStateOf("") }
    var page by remember { mutableStateOf("Tests") }
    var busy by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var exam by remember { mutableStateOf<DigitalTest?>(null) }
    var examStartedAtMillis by remember { mutableStateOf(0L) }
    var savedAttemptPending by remember { mutableStateOf(false) }
    var mockRetryAvailable by remember { mutableStateOf(false) }
    var submissionStage by remember { mutableStateOf("Ready to submit") }
    var submissionProgress by remember { mutableStateOf(0f) }
    var showSubmissionResult by remember { mutableStateOf(false) }
    var questions by remember { mutableStateOf<List<DigitalQuestion>>(emptyList()) }
    var result by remember { mutableStateOf<JSONObject?>(null) }
    var report by remember { mutableStateOf<JSONObject?>(null) }
    var reportStudent by remember { mutableStateOf<StudentRating?>(null) }
    var reportIsClassTeacher by remember { mutableStateOf(false) }
    var progressReport by remember { mutableStateOf<JSONObject?>(null) }
    var progressReportStudent by remember { mutableStateOf<StudentRating?>(null) }
    var progressReportClassId by remember { mutableStateOf("") }
    var reviewAttempt by remember { mutableStateOf<JSONObject?>(null) }
    var reviewTitle by remember { mutableStateOf("") }
    var showBuilder by remember { mutableStateOf(false) }
    var editingTest by remember { mutableStateOf<DigitalTest?>(null) }
    var editingQuestions by remember { mutableStateOf(emptyList<DraftQuestion>()) }
    var showAdminDialog by remember { mutableStateOf<String?>(null) }
    var showMetricDialog by remember { mutableStateOf(false) }
    val tests = remember { mutableStateListOf<DigitalTest>() }
    val analyses = remember { mutableStateListOf<TestAnalysis>() }
    val ratings = remember { mutableStateListOf<StudentRating>() }
    var ratingsClassId by remember { mutableStateOf("") }
    val teacherMetrics = remember { mutableStateListOf<JSONObject>() }
    val adminUsers = remember { mutableStateListOf<JSONObject>() }
    val answers = remember { mutableStateMapOf<String, String>() }
    var editingAdminUser by remember { mutableStateOf<JSONObject?>(null) }
    val classes = user?.classes.orEmpty()
    val activeClass = classes.firstOrNull { it.id == selectedClassId } ?: classes.firstOrNull()
    val student = user?.role == "student"

    fun showError(message: String) { activity.runOnUiThread { error = message } }
    val perform: (String, () -> Unit) -> Unit = { title, work ->
        if (!busy) {
            busy = true
            executor.execute {
                try { work() } catch (failure: Exception) {
                    Log.e(ClassroomLog, "$title failed", failure)
                    showError(failure.message ?: "$title failed. Try again.")
                } finally { activity.runOnUiThread { busy = false } }
            }
        }
    }
    fun refresh(current: SignedInUser, classId: String) {
        val api = SmartclassApi(backendUrl, current.token)
        val newTests = if (current.isAdmin) emptyList() else parseTests(api.tests(classId))
        val newAnalyses = if (current.role == "student") parseAnalyses(api.myAnalyses()) else emptyList()
        val newRatings = if (current.role == "teacher" && !current.isAdmin) parseRatings(api.classRatings(classId)) else emptyList()
        val metricSubjects = if (current.role == "teacher" && !current.isAdmin) current.classes.firstOrNull { it.id == classId }?.subjects.orEmpty() else emptyList()
        val newMetrics = metricSubjects.flatMap { subject ->
            val rows = api.metrics(classId, subject)
            (0 until rows.length()).map { index -> rows.getJSONObject(index) }
        }
            val directory = if (current.isAdmin) api.adminUsers() else JSONArray()
            val newAdminUsers = (0 until directory.length()).map { directory.getJSONObject(it) }
        activity.runOnUiThread {
            tests.clear(); tests.addAll(newTests)
            analyses.clear(); analyses.addAll(newAnalyses)
            ratings.clear(); ratings.addAll(newRatings)
            ratingsClassId = classId
            teacherMetrics.clear(); teacherMetrics.addAll(newMetrics)
            adminUsers.clear(); adminUsers.addAll(newAdminUsers)
        }
    }
    fun openExam(test: DigitalTest, current: SignedInUser) = perform("Could not open test") {
        val body = SmartclassApi(backendUrl, current.token).digitalTest(test.id)
        val parsed = parseQuestions(body.getJSONArray("questions"))
        val pendingAttempt = body.optJSONObject("my_attempt")
        activity.runOnUiThread {
            exam = test
            examStartedAtMillis = System.currentTimeMillis()
            questions = parsed
            answers.clear()
            if (pendingAttempt != null) {
                val saved = pendingAttempt.getJSONObject("answers")
                val savedKeys = saved.keys()
                while (savedKeys.hasNext()) {
                    val key = savedKeys.next()
                    answers[key] = saved.get(key).toString()
                }
            }
            savedAttemptPending = pendingAttempt?.optString("status") == "submitted"
            mockRetryAvailable = false
            result = null
        }
    }
    fun submitExam(current: SignedInUser, selected: DigitalTest, currentAnswers: Map<String, String>) {
        mockRetryAvailable = false
        submissionStage = "Submitting your answers"
        submissionProgress = 0.05f
        showSubmissionResult = false
        perform("Could not submit test") {
            val answerJson = JSONObject()
            questions.forEach { question ->
                val value = currentAnswers[question.id].orEmpty()
                if (question.type == "mcq") answerJson.put(question.id, value.toIntOrNull() ?: JSONObject.NULL) else answerJson.put(question.id, value)
            }
            val api = SmartclassApi(backendUrl, current.token)
            val response = try {
                api.submitTest(selected.id, answerJson, selected.isMock)
            } catch (failure: Exception) {
                if (selected.isMock) {
                    activity.runOnUiThread {
                        mockRetryAvailable = true
                        submissionStage = "Analysis could not be completed"
                        error = "The response could not be read or analysis failed. Your answers are still here; tap Retry mock analysis to try again."
                    }
                    return@perform
                }
                val saved = api.digitalTest(selected.id).optJSONObject("my_attempt")
                if (saved?.optString("status") == "submitted") {
                    val savedAnswers = saved.getJSONObject("answers")
                    activity.runOnUiThread {
                        answers.clear()
                        val keys = savedAnswers.keys()
                        while (keys.hasNext()) {
                            val key = keys.next()
                            answers[key] = savedAnswers.get(key).toString()
                        }
                        savedAttemptPending = true
                    }
                }
                throw failure
            }
            if (!selected.isMock) refresh(current, selectedClassId)
            activity.runOnUiThread {
                result = response
                savedAttemptPending = false
                mockRetryAvailable = false
                submissionStage = "Analysis complete"
                submissionProgress = 1f
                showSubmissionResult = false
            }
        }
    }
    fun openStudentReport(item: StudentRating, current: SignedInUser, asOf: String? = null, subject: String? = null) = perform("Could not open student analysis") {
        val response = SmartclassApi(backendUrl, current.token).studentAnalysis(selectedClassId, item.id, asOf, subject)
        val isClassTeacher = current.isAdmin || current.classes.firstOrNull { it.id == selectedClassId }?.isClassTeacher == true
        activity.runOnUiThread { reportStudent = item; report = response; reportIsClassTeacher = isClassTeacher }
    }
    fun returnToHome() {
        result = null
        exam = null
        questions = emptyList()
        answers.clear()
        savedAttemptPending = false
        mockRetryAvailable = false
        page = "Tests"
    }

    BackHandler(enabled = result != null) { returnToHome() }

    LaunchedEffect(busy, exam?.id, result) {
        if (busy && exam != null && result == null) {
            val stages = listOf(
                0.18f to "Submitting your answers",
                0.38f to "AI is reading your answers",
                0.62f to "Checking responses and answer keys",
                0.82f to "Preparing your analysis"
            )
            for ((target, label) in stages) {
                delay(1100)
                if (!busy || result != null) break
                submissionStage = label
                submissionProgress = maxOf(submissionProgress, target)
            }
            while (busy && result == null && submissionProgress < 0.94f) {
                delay(700)
                if (busy && result == null) submissionProgress = (submissionProgress + 0.012f).coerceAtMost(0.94f)
            }
        }
    }

    LaunchedEffect(result) {
        showSubmissionResult = false
        if (result != null) {
            submissionStage = "Analysis complete"
            submissionProgress = 1f
            delay(750)
            showSubmissionResult = true
        }
    }

    MaterialTheme {
        Surface(color = Paper, modifier = Modifier.fillMaxSize()) {
            val current = user
            when {
                current == null -> LoginPanel(busy, { username, password ->
                    perform("Sign in failed") {
                        val response = SmartclassApi(backendUrl).login(username, password)
                        val profile = response.getJSONObject("user")
                        val classList = response.optJSONArray("classes") ?: JSONArray()
                        val allParsedClasses = (0 until classList.length()).map { index -> classList.getJSONObject(index).let { SchoolClass(it.getString("id"), it.getString("name"), it.optString("year"), it.optBoolean("is_class_teacher"), stringList(it.optJSONArray("subjects"))) } }
                        val parsedClasses = if (profile.optString("role") == "student") allParsedClasses.take(1) else allParsedClasses
                        val logged = SignedInUser(profile.getString("id"), profile.getString("name"), profile.getString("username"), profile.getString("role"), profile.optBoolean("is_admin"), response.getString("access_token"), parsedClasses)
                        val firstClass = parsedClasses.firstOrNull()
                        if (firstClass != null) refresh(logged, firstClass.id)
                        activity.runOnUiThread { user = logged; selectedClassId = firstClass?.id.orEmpty(); page = if (logged.isAdmin) "Admin" else "Tests" }
                    }
                })
                exam != null && result == null -> ExamPanel(
                    test = exam!!,
                    questions = questions,
                    answers = answers,
                    readOnly = savedAttemptPending || busy,
                    retryAvailable = mockRetryAvailable,
                    busy = busy,
                    submissionStage = submissionStage,
                    submissionProgress = submissionProgress,
                    startedAtMillis = examStartedAtMillis,
                    onAnswer = { id, value -> answers[id] = value },
                    onSubmit = { currentAnswers -> submitExam(current, exam!!, currentAnswers) },
                    onExit = { exam = null; questions = emptyList(); answers.clear(); savedAttemptPending = false }
                )
                result != null && !showSubmissionResult -> SubmissionProgressPanel(submissionStage, submissionProgress)
                result != null -> ResultPanel(result!!, exam?.isMock == true, onHome = ::returnToHome)
                else -> PortalPanel(
                    user = current,
                    activeClass = activeClass,
                    classes = classes,
                    page = page,
                    busy = busy,
                    tests = tests,
                    analyses = analyses,
                    ratings = ratings,
                    metrics = teacherMetrics,
                    adminUsers = adminUsers,
                    progressReport = progressReport,
                    progressReportStudentId = progressReportStudent?.id,
                    progressReportClassId = progressReportClassId,
                    ratingsClassId = ratingsClassId,
                    onClass = { selectedClassId = it; val selected = current.classes.firstOrNull { item -> item.id == it }; if (selected != null) perform("Could not refresh class") { refresh(current, selected.id) } },
                    onPage = { page = it },
                    onLogout = { user = null; tests.clear(); analyses.clear(); ratings.clear(); progressReport = null; progressReportStudent = null },
                    onProgress = { item ->
                        progressReport = null
                        progressReportStudent = item
                        progressReportClassId = selectedClassId
                        perform("Could not load student progress") {
                            val payload = SmartclassApi(backendUrl, current.token).studentAnalysis(selectedClassId, item.id)
                            activity.runOnUiThread { progressReport = payload }
                        }
                    },
                    onOpenTest = { openExam(it, current) },
                    onReviewAttempt = { test ->
                        perform("Could not load your test review") {
                            val payload = SmartclassApi(backendUrl, current.token).attemptReview(test.id)
                            activity.runOnUiThread { reviewAttempt = payload; reviewTitle = test.title }
                        }
                    },
                    onOpenBuilder = { editingTest = null; editingQuestions = emptyList(); showBuilder = true },
                    onEditTest = { selectedTest ->
                        perform("Could not open test for editing") {
                            val body = SmartclassApi(backendUrl, current.token).digitalTest(selectedTest.id)
                            val draft = parseDraftQuestions(body.getJSONArray("questions"))
                            activity.runOnUiThread { editingTest = selectedTest; editingQuestions = draft; showBuilder = true }
                        }
                    },
                    onDeleteTest = { selectedTest ->
                        perform("Could not delete test") {
                            SmartclassApi(backendUrl, current.token).deleteDigitalTest(selectedTest.id)
                            refresh(current, selectedClassId)
                        }
                    },
                    onReport = { item, subject -> openStudentReport(item, current, subject = subject) },
                    onReviewStudentAttempt = { test, studentId ->
                        perform("Could not load this student submission") {
                            val payload = SmartclassApi(backendUrl, current.token).attemptReview(test.id, studentId)
                            activity.runOnUiThread { reviewAttempt = payload; reviewTitle = test.title }
                        }
                    },
                    onAddStudent = { showAdminDialog = "student" },
                    onAddTeacher = { showAdminDialog = "teacher" },
                    onEditUser = { editingAdminUser = it; showAdminDialog = "update" },
                    onDeleteUser = { selected ->
                        perform("Could not delete account") {
                            SmartclassApi(backendUrl, current.token).adminDeleteUser(selected.getString("id"))
                            refresh(current, selectedClassId)
                        }
                    },
                    onCreateMetric = { showMetricDialog = true }
                )
            }
        }
    }
    if (reviewAttempt != null) ReviewAttemptDialog(title = reviewTitle, payload = reviewAttempt!!, onDismiss = { reviewAttempt = null; reviewTitle = "" })
    if (showBuilder) TestBuilderDialog(existingTest = editingTest, initialQuestions = editingQuestions, subjects = activeClass?.subjects.orEmpty(), onDismiss = { showBuilder = false; editingTest = null; editingQuestions = emptyList() }, onPublish = { existingTest, title, subject, kind, dueDate, durationMinutes, draft ->
        val publisher = user ?: return@TestBuilderDialog
        if (draft.isEmpty()) { error = "Add at least one question before publishing." }
        if (draft.isNotEmpty()) {
            val apiUser = publisher
            perform("Could not publish test") {
                val api = SmartclassApi(backendUrl, apiUser.token)
                if (existingTest != null) {
                    val questionBodies = JSONArray()
                    draft.forEachIndexed { index, question ->
                        questionBodies.put(JSONObject().put("prompt", question.prompt).put("points", question.points).put("question_type", question.type).put("options", JSONArray(question.options)).put("answer_key", question.answerKey).put("position", index + 1))
                    }
                    api.replaceDigitalTest(existingTest.id, JSONObject().put("title", title).put("subject", subject).put("kind", kind).put("due_date", dueDate).put("duration_minutes", durationMinutes).put("questions", questionBodies))
                } else {
                    val created = api.createDigitalTest(selectedClassId, title, subject, kind, dueDate, false, durationMinutes)
                    val newTestId = created.getString("id")
                    draft.forEachIndexed { index, question ->
                        val body = JSONObject().put("prompt", question.prompt).put("points", question.points).put("question_type", question.type).put("options", JSONArray(question.options)).put("answer_key", question.answerKey).put("position", index + 1)
                        api.addQuestion(newTestId, body)
                    }
                    api.publishTest(newTestId)
                }
                refresh(apiUser, selectedClassId)
                activity.runOnUiThread { showBuilder = false; editingTest = null; editingQuestions = emptyList() }
            }
        }
    })
    if (report != null && reportStudent != null) AnalysisDialog(report!!, reportStudent!!, reportIsClassTeacher, onSearch = { date, subject ->
        val current = user ?: return@AnalysisDialog
        openStudentReport(reportStudent!!, current, date.takeIf(String::isNotBlank), subject)
    }, onDismiss = { report = null; reportStudent = null; reportIsClassTeacher = false })
    if (showAdminDialog != null) AdminDialog(showAdminDialog!!, classes, classes.flatMap { it.subjects }.distinct().sorted(), editingAdminUser, onDismiss = { showAdminDialog = null; editingAdminUser = null }, onSave = { form ->
        val mode = showAdminDialog ?: return@AdminDialog
        val currentUser = user ?: return@AdminDialog
        perform("Admin action failed") {
            val api = SmartclassApi(backendUrl, currentUser.token)
            when (mode) {
                "class" -> api.adminCreateClass(form.getString("name"), form.getString("year"))
                "student" -> api.adminCreateStudent(form.getString("username"), form.getString("name"), form.getString("password"), form.getString("class_id"))
                "teacher" -> api.adminCreateTeacher(form.getString("username"), form.getString("name"), form.getString("password"), form.getJSONArray("assignments"))
                "update" -> {
                    val updates = JSONObject().put("name", form.getString("name"))
                    form.optString("new_username").takeIf(String::isNotBlank)?.let { updates.put("username", it) }
                    form.optString("password").takeIf(String::isNotBlank)?.let { updates.put("password", it) }
                    form.optString("class_id").takeIf(String::isNotBlank)?.let { updates.put("class_id", it) }
                    api.adminUpdateUser(form.getString("id"), updates)
                    if (form.has("assignments")) api.adminSetTeacherAssignments(form.getString("id"), form.getJSONArray("assignments"))
                }
                else -> api.adminAssignTeacher(form.getString("teacher_id"), form.getString("class_id"), form.getString("assignment_type"), form.optString("subject").takeIf { it.isNotBlank() })
            }
            val refreshedUser = if (mode == "class") {
                val latest = api.adminClasses()
                val newClasses = (0 until latest.length()).map { index -> latest.getJSONObject(index).let { SchoolClass(it.getString("id"), it.getString("name"), it.optString("year")) } }
                currentUser.copy(classes = newClasses)
            } else currentUser
            if (mode == "class") activity.runOnUiThread { user = refreshedUser }
            refresh(refreshedUser, selectedClassId)
            activity.runOnUiThread { showAdminDialog = null; editingAdminUser = null }
        }
    })
    if (showMetricDialog) MetricDialog(activeClass?.subjects.orEmpty(), onDismiss = { showMetricDialog = false }, onSave = { subject, name, description ->
        val currentUser = user ?: return@MetricDialog
        perform("Could not save metric") {
            SmartclassApi(backendUrl, currentUser.token).createMetric(selectedClassId, subject, name, description, 1.0)
            refresh(currentUser, selectedClassId)
            activity.runOnUiThread { showMetricDialog = false }
        }
    })
    error?.let { message -> AlertDialog(onDismissRequest = { error = null }, title = { Text("Smartclass") }, text = { Text(message) }, confirmButton = { TextButton(onClick = { error = null }) { Text("OK") } }) }
}

@Composable
private fun LoginPanel(busy: Boolean, onLogin: (String, String) -> Unit) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    var showPassword by remember { mutableStateOf(false) }
    Box(Modifier.fillMaxSize().background(Paper).imePadding(), contentAlignment = Alignment.Center) {
        Column(
            Modifier.fillMaxWidth().widthIn(max = 440.dp).verticalScroll(rememberScrollState()).padding(horizontal = 26.dp, vertical = 24.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Box(Modifier.background(Green, CircleShape).padding(10.dp)) {
                    Icon(Icons.Default.School, contentDescription = null, tint = Teal)
                }
                Column {
                    Text("AI SMARTCLASS", color = Teal, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                    Text("SCHOOL PORTAL", color = Muted, fontWeight = FontWeight.Medium, fontSize = 9.sp)
                }
            }
            Spacer(Modifier.height(5.dp))
            Box(Modifier.width(34.dp).height(4.dp).background(Coral, RoundedCornerShape(2.dp)))
            Text("Your classroom,\nready when you are.", color = Ink, fontSize = 32.sp, lineHeight = 38.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
            Text("Sign in to continue to your class work.", color = Muted, fontSize = 13.sp)
            OutlinedTextField(
                value = username,
                onValueChange = { username = it },
                label = { Text("Username") },
                leadingIcon = { Icon(Icons.Default.PersonOutline, contentDescription = null, tint = Teal) },
                singleLine = true,
                modifier = Modifier.fillMaxWidth()
            )
            OutlinedTextField(
                value = password,
                onValueChange = { password = it },
                label = { Text("Password") },
                leadingIcon = { Icon(Icons.Default.Lock, contentDescription = null, tint = Teal) },
                trailingIcon = {
                    IconButton(onClick = { showPassword = !showPassword }) {
                        Icon(if (showPassword) Icons.Default.VisibilityOff else Icons.Default.Visibility, contentDescription = if (showPassword) "Hide password" else "Show password", tint = Muted)
                    }
                },
                singleLine = true,
                visualTransformation = if (showPassword) androidx.compose.ui.text.input.VisualTransformation.None else PasswordVisualTransformation(),
                keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password),
                modifier = Modifier.fillMaxWidth()
            )
            Button(
                onClick = { onLogin(username.trim(), password) },
                enabled = !busy && username.isNotBlank() && password.isNotBlank(),
                colors = ButtonDefaults.buttonColors(containerColor = Teal),
                modifier = Modifier.fillMaxWidth().height(50.dp),
                shape = RoundedCornerShape(9.dp)
            ) {
                if (busy) CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.width(20.dp).height(20.dp))
                else Text("Sign in", color = Color.White, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun PortalPanel(
    user: SignedInUser, activeClass: SchoolClass?, classes: List<SchoolClass>, page: String, busy: Boolean,
    tests: List<DigitalTest>, analyses: List<TestAnalysis>, ratings: List<StudentRating>, metrics: List<JSONObject>, adminUsers: List<JSONObject>,
    progressReport: JSONObject?, progressReportStudentId: String?, progressReportClassId: String, ratingsClassId: String,
    onClass: (String) -> Unit, onPage: (String) -> Unit, onLogout: () -> Unit,
    onProgress: (StudentRating) -> Unit,
    onOpenTest: (DigitalTest) -> Unit, onReviewAttempt: (DigitalTest) -> Unit, onOpenBuilder: () -> Unit, onEditTest: (DigitalTest) -> Unit, onDeleteTest: (DigitalTest) -> Unit,
    onReport: (StudentRating, String?) -> Unit, onReviewStudentAttempt: (DigitalTest, String) -> Unit, onAddStudent: () -> Unit, onAddTeacher: () -> Unit,
    onEditUser: (JSONObject) -> Unit, onDeleteUser: (JSONObject) -> Unit, onCreateMetric: () -> Unit
) {
    val admin = user.isAdmin
    val teacher = user.role == "teacher" && !admin
    val navItems = if (admin) listOf("Admin", "Profile") else if (teacher) listOf("Tests", "Class", "Progress", "Metrics", "Profile") else listOf("Tests", "Results", "Mock", "Profile")
    var testSubject by remember(user.id, activeClass?.id) { mutableStateOf("") }
    var resultSubject by remember(user.id, activeClass?.id) { mutableStateOf("") }
    var mockSubject by remember(user.id, activeClass?.id) { mutableStateOf("") }
    var classSubject by remember(user.id, activeClass?.id) { mutableStateOf("") }
    var progressStudentId by remember(user.id, activeClass?.id) { mutableStateOf("") }
    var adminClassFilter by remember(user.id) { mutableStateOf("All classes") }
    var adminRoleFilter by remember(user.id) { mutableStateOf("All roles") }
    var pendingDeleteUser by remember { mutableStateOf<JSONObject?>(null) }
    var pendingDeleteTest by remember { mutableStateOf<DigitalTest?>(null) }
    fun classLabel(item: SchoolClass) = if (teacher && item.isClassTeacher) "${item.name} (Class Teacher)" else item.name
    val selectedProgressStudent = ratings.firstOrNull { it.id == progressStudentId } ?: ratings.firstOrNull()
    Column(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.weight(1f), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 18.dp, vertical = 12.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                    Column(Modifier.weight(1f)) {
                        Text("SMARTCLASS  /  ${if (admin) "SCHOOL" else activeClass?.name?.uppercase() ?: "NO CLASS"}", color = Teal, fontWeight = FontWeight.Bold, fontSize = 10.sp)
                        Text("Good morning, ${user.name}", color = Teal, fontSize = 14.sp, fontWeight = FontWeight.Medium)
                        Text(if (admin) "School admin" else "${if (teacher) "Teacher" else "Student"} portal", color = Ink, fontSize = 28.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
                    }
                    TextButton(onClick = onLogout) { Text("Sign out", color = Teal) }
                }
            }
            item {
                Row(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(10.dp)).padding(4.dp), horizontalArrangement = Arrangement.spacedBy(3.dp)) {
                    navItems.forEach { item ->
                        Box(
                            Modifier.weight(1f).clip(RoundedCornerShape(7.dp)).background(if (item == page) Teal else Color.Transparent)
                                .clickable { onPage(item) }.padding(horizontal = 2.dp, vertical = 9.dp),
                            contentAlignment = Alignment.Center
                        ) {
                            Text(item, color = if (item == page) Color.White else Muted, fontSize = 10.sp, fontWeight = if (item == page) FontWeight.SemiBold else FontWeight.Medium, maxLines = 1)
                        }
                    }
                }
            }
            if (busy) item { Row(verticalAlignment = Alignment.CenterVertically) { CircularProgressIndicator(color = Teal, strokeWidth = 2.dp, modifier = Modifier.width(18.dp).height(18.dp)); Text("  Updating class data...", color = Muted, fontSize = 12.sp) } }
            when (page) {
                "Results" -> {
                    item { Heading("Your test results", "PER-TEST RATINGS ONLY") }
                    val subjects = analyses.map { it.subject }.distinct().sorted()
                    item { ChoiceDropdown("Subject", resultSubject.ifBlank { "Select subject" }, subjects, { resultSubject = it }) }
                    val filtered = analyses.filter { it.subject == resultSubject }
                    if (resultSubject.isBlank()) item { BlankState("Choose a subject", "Select a subject to see its test results.") }
                    else if (filtered.isEmpty()) item { BlankState("No results for this subject", "Your analyzed tests will appear here.") }
                    items(filtered) { AnalysisCard(it) }
                }
                "Profile" -> {
                    item { Heading("Your profile", "ACCOUNT DETAILS") }
                    item { ProfileDetails(user, classes) }
                }
                "Class" -> {
                    if (teacher || admin) item { ChoiceDropdown("Class", activeClass?.let(::classLabel).orEmpty(), classes.map(::classLabel), { selected -> classes.firstOrNull { classLabel(it) == selected }?.let { onClass(it.id) } }) }
                    item { Heading("Student progress", "${ratings.size} STUDENTS") }
                    val subjects = ratings.flatMap { rating -> rating.subjects.keys().asSequence().toList() }.distinct().sorted()
                    val subjectOnlyClass = teacher && activeClass?.isClassTeacher == false
                    val classSubjectOptions = if (subjectOnlyClass) activeClass?.subjects.orEmpty() else subjects
                    val selectedClassSubject = classSubject.ifBlank { classSubjectOptions.firstOrNull().orEmpty() }
                    if (subjectOnlyClass && classSubjectOptions.size > 1) item { ChoiceDropdown("Subject", selectedClassSubject.ifBlank { "Select subject" }, classSubjectOptions, { classSubject = it }) }
                    if (ratings.isEmpty()) item { BlankState("No class ratings", "Ratings appear as assessments are completed.") }
                    items(ratings) { item -> RatingCard(item, selectedClassSubject.takeIf { subjectOnlyClass }) { onReport(item, selectedClassSubject.takeIf { subjectOnlyClass }) } }
                }
                "Progress" -> {
                    item { ChoiceDropdown("Class", activeClass?.let(::classLabel).orEmpty(), classes.map(::classLabel), { selected -> classes.firstOrNull { classLabel(it) == selected }?.let { onClass(it.id) } }) }
                    item { Heading("Student progress", "ASSESSMENT TRENDS") }
                    if (ratingsClassId != activeClass?.id) {
                        item { BlankState("Loading class roster", "Student choices update when the selected class finishes loading.") }
                    } else if (ratings.isEmpty()) {
                        item { BlankState("No student data yet", "Progress charts appear after students complete analyzed assessments.") }
                    } else {
                        item {
                            ChoiceDropdown("Student", selectedProgressStudent?.name.orEmpty(), ratings.map { it.name }) { name ->
                                progressStudentId = ratings.firstOrNull { it.name == name }?.id.orEmpty()
                            }
                        }
                        item {
                            Button(onClick = { selectedProgressStudent?.let(onProgress) }, enabled = !busy && ratingsClassId == activeClass?.id && selectedProgressStudent != null, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Teal), shape = RoundedCornerShape(8.dp)) {
                                Icon(Icons.Default.ShowChart, contentDescription = null, tint = Color.White)
                                Text(if (busy) "  Loading progress..." else "  View progress", color = Color.White)
                            }
                        }
                        if (selectedProgressStudent != null) {
                            val visibleReport = progressReport.takeIf {
                                progressReportStudentId == selectedProgressStudent.id && progressReportClassId == activeClass?.id
                            }
                            if (visibleReport == null) {
                                item { BlankState("Loading progress", "Preparing ${selectedProgressStudent.name}'s assessment history.") }
                            } else {
                                item {
                                    StudentProgressDashboard(
                                        report = visibleReport,
                                        student = selectedProgressStudent,
                                        isClassTeacher = activeClass?.isClassTeacher == true,
                                    )
                                }
                            }
                        }
                    }
                }
                "Metrics" -> {
                    if (teacher) item { ChoiceDropdown("Class", activeClass?.let(::classLabel).orEmpty(), classes.map(::classLabel), { selected -> classes.firstOrNull { classLabel(it) == selected }?.let { onClass(it.id) } }) }
                    item { Heading("Subject metrics", "TEACHER-DEFINED RATINGS") }
                    item { ActionButton("Add a rating metric", onCreateMetric) }
                    val subjects = if (admin) tests.map { it.subject }.distinct().sorted() else activeClass?.subjects.orEmpty()
                    if (subjects.size > 1) item { ChoiceDropdown("Subject", classSubject.ifBlank { "Select subject" }, subjects, { classSubject = it }) }
                    val selectedSubject = classSubject.ifBlank { subjects.firstOrNull().orEmpty() }
                    val visibleMetrics = metrics.filter { it.optString("subject") == selectedSubject }
                    if (visibleMetrics.isEmpty()) item { BlankState("No metrics for this subject", "Teacher-defined ratings for this class and subject appear here.") }
                    items(visibleMetrics, key = { it.getString("id") }) { metric ->
                        Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(6.dp)).padding(14.dp)) {
                            Text(metric.optString("name"), color = Ink, fontWeight = FontWeight.SemiBold)
                            Text(metric.optString("description"), color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                        }
                    }
                }
                "Admin" -> {
                    item { Heading("People directory", "STUDENTS AND TEACHERS") }
                    val adminClassOptions = listOf("All classes") + classes.map(::classLabel)
                    item { ChoiceDropdown("Class", adminClassFilter, adminClassOptions, { adminClassFilter = it }) }
                    item { ChoiceDropdown("People", adminRoleFilter, listOf("All roles", "Students", "Teachers"), { adminRoleFilter = it }) }
                    item { Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) { Button(onClick = onAddStudent, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Teal)) { Text("Add student", color = Color.White) }; Button(onClick = onAddTeacher, modifier = Modifier.weight(1f), colors = ButtonDefaults.buttonColors(containerColor = Teal)) { Text("Add teacher", color = Color.White) } } }
                    val filteredAccounts = adminUsers.filter { account ->
                        val roleMatches = when (adminRoleFilter) {
                            "Students" -> account.optString("role") == "student"
                            "Teachers" -> account.optString("role") == "teacher"
                            else -> true
                        }
                        val selectedClassId = classes.firstOrNull { classLabel(it) == adminClassFilter }?.id
                        val assignedToClass = account.optJSONArray("assignments")?.let { assignments -> (0 until assignments.length()).any { index -> assignments.getJSONObject(index).optString("class_name") == adminClassFilter } } ?: false
                        val classMatches = adminClassFilter == "All classes" || account.optString("class_id") == selectedClassId || account.optString("class_name") == adminClassFilter || assignedToClass
                        roleMatches && classMatches
                    }
                    items(filteredAccounts, key = { it.getString("id") }) { account ->
                        val assignments = account.optJSONArray("assignments") ?: JSONArray()
                        val assignmentText = (0 until assignments.length()).map { index ->
                            val assignment = assignments.getJSONObject(index)
                            "${assignment.optString("class_name")} · ${if (assignment.optString("assignment_type") == "class") "Class teacher" else assignment.optString("subject")}"
                        }.joinToString("; ")
                        Row(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(6.dp)).padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(account.optString("name"), color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                                Text("${account.optString("username")} · ${account.optString("role")} · ${if (account.optString("role") == "student") account.optString("class_name", "No class assigned") else assignmentText.ifBlank { "No active class assignment" }}", color = Muted, fontSize = 10.sp)
                            }
                            TextButton(onClick = { onEditUser(account) }) { Text("Edit", color = Teal) }
                            TextButton(onClick = { pendingDeleteUser = account }) { Text("Delete", color = Coral) }
                        }
                    }
                    item { BlankState("School-wide directory", "${adminUsers.count { it.optString("role") == "student" }} students · ${adminUsers.count { it.optString("role") == "teacher" }} teachers") }
                }
                else -> {
                    if (teacher || admin) item { ChoiceDropdown("Class", activeClass?.let(::classLabel).orEmpty(), classes.map(::classLabel), { selected -> classes.firstOrNull { classLabel(it) == selected }?.let { onClass(it.id) } }) }
                    val mockPage = page == "Mock"
                    val available = tests.filter { it.isMock == mockPage }
                    val subjects = if (teacher && !mockPage) activeClass?.subjects.orEmpty() else available.map { it.subject }.distinct().sorted()
                    item { Heading(if (teacher || admin) "Digital assessments" else if (mockPage) "Practice tests" else "Class assessments", if (teacher || admin) "YOUR CLASS AND TESTS" else "SELECT A SUBJECT") }
                    if (teacher) item { ActionButton("Create a digital test", onOpenBuilder) }
                    item { ChoiceDropdown("Subject", (if (mockPage) mockSubject else testSubject).ifBlank { "Select subject" }, subjects, { selected -> if (mockPage) mockSubject = selected else testSubject = selected }) }
                    val selection = if (mockPage) mockSubject else testSubject
                    val filtered = available.filter { it.subject == selection }
                    if (selection.isBlank()) item { BlankState("Choose a subject", "Tests will appear after you select their subject.") }
                    else if (filtered.isEmpty()) item { BlankState("No tests available", "There are no published ${if (mockPage) "mock" else "regular"} tests for this subject.") }
                    items(filtered, key = { it.id }) { test -> TestCard(test, teacher || admin, onOpenTest, onReviewAttempt, onEditTest, { pendingDeleteTest = it }, onReviewStudentAttempt) }
                }
            }
        }
    }
    pendingDeleteUser?.let { account ->
        AlertDialog(onDismissRequest = { pendingDeleteUser = null }, title = { Text("Delete ${account.optString("name")}?") }, text = { Text("This permanently removes the ${account.optString("role")} profile and its sign-in access.") }, confirmButton = { TextButton(onClick = { pendingDeleteUser = null; onDeleteUser(account) }) { Text("Delete", color = Coral) } }, dismissButton = { TextButton(onClick = { pendingDeleteUser = null }) { Text("Cancel", color = Muted) } })
    }
    pendingDeleteTest?.let { test ->
        AlertDialog(onDismissRequest = { pendingDeleteTest = null }, title = { Text("Delete ${test.title}?") }, text = { Text("The test will be hidden from students. Existing analysis history will be retained.") }, confirmButton = { TextButton(onClick = { pendingDeleteTest = null; onDeleteTest(test) }) { Text("Delete", color = Coral) } }, dismissButton = { TextButton(onClick = { pendingDeleteTest = null }) { Text("Cancel", color = Muted) } })
    }
}

@Composable
private fun Heading(title: String, eyebrow: String) {
    Column(Modifier.fillMaxWidth()) { Text(eyebrow, color = Teal, fontSize = 9.sp, fontWeight = FontWeight.Bold); Text(title, color = Ink, fontSize = 23.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold) }
}

@Composable
private fun ChoiceDropdown(label: String, value: String, options: List<String>, onSelect: (String) -> Unit) {
    var expanded by remember(label) { mutableStateOf(false) }
    Box(Modifier.fillMaxWidth()) {
        OutlinedButton(onClick = { expanded = true }, enabled = options.isNotEmpty(), modifier = Modifier.fillMaxWidth()) {
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                Column(horizontalAlignment = Alignment.Start) {
                    Text(label, color = Muted, fontSize = 10.sp)
                    Text(value.ifBlank { "Choose" }, color = Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                }
                Text("▾", color = Teal, fontSize = 16.sp)
            }
        }
        DropdownMenu(expanded = expanded, onDismissRequest = { expanded = false }, modifier = Modifier.fillMaxWidth(0.92f)) {
            options.distinct().forEach { option ->
                DropdownMenuItem(text = { Text(option, color = Ink) }, onClick = { expanded = false; onSelect(option) })
            }
        }
    }
}

@Composable
private fun TestCard(test: DigitalTest, teacher: Boolean, onOpen: (DigitalTest) -> Unit, onReviewAttempt: (DigitalTest) -> Unit, onEdit: (DigitalTest) -> Unit, onDelete: (DigitalTest) -> Unit, onReviewStudentAttempt: (DigitalTest, String) -> Unit) {
    Column(Modifier.fillMaxWidth().background(Panel, RoundedCornerShape(12.dp)).padding(15.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(test.subject.uppercase(), color = Teal, fontSize = 10.sp, fontWeight = FontWeight.Bold); Text(if (test.isMock) "MOCK" else test.dueDate, color = Muted, fontSize = 10.sp) }
        Text(test.title, color = Ink, fontSize = 18.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 5.dp))
        Text("${test.questionCount} questions  ·  ${test.kind}", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 3.dp, bottom = 10.dp))
        if (teacher) {
            Text("${test.studentsTaken} students have attempted this test", color = Muted, fontSize = 11.sp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                if (!test.isMock) TextButton(onClick = { onReviewAttempt(test) }) { Text("Review", color = Teal) }
                if (test.studentsTaken == 0 && !test.isMock) TextButton(onClick = { onEdit(test) }) { Text("Edit", color = Teal) }
                if (!test.isMock) TextButton(onClick = { onDelete(test) }) { Text("Delete", color = Coral) }
            }
        } else {
            val action = when { test.isMock -> "Try mock test"; test.pending -> "Retry AI analysis"; test.completed -> "Review submission"; else -> "Start test" }
            Button(onClick = { if (test.completed) onReviewAttempt(test) else onOpen(test) }, enabled = test.isMock || !test.completed || test.completed, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Teal), shape = RoundedCornerShape(8.dp)) { Text(action, color = Color.White) }
        }
    }
}

@Composable
private fun ExamPanel(test: DigitalTest, questions: List<DigitalQuestion>, answers: Map<String, String>, readOnly: Boolean, retryAvailable: Boolean, busy: Boolean, submissionStage: String, submissionProgress: Float, startedAtMillis: Long, onAnswer: (String, String) -> Unit, onSubmit: (Map<String, String>) -> Unit, onExit: () -> Unit) {
    var remainingSeconds by remember(test.id, startedAtMillis) { mutableStateOf(test.durationMinutes.coerceAtLeast(1) * 60) }
    var autoSubmitted by remember(test.id, startedAtMillis) { mutableStateOf(false) }
    val latestAnswers = rememberUpdatedState(answers)
    val latestSubmit = rememberUpdatedState(onSubmit)
    LaunchedEffect(test.id, startedAtMillis, readOnly) {
        if (startedAtMillis > 0 && !readOnly && !autoSubmitted) {
            while (remainingSeconds > 0) {
                val elapsed = ((System.currentTimeMillis() - startedAtMillis) / 1000).toInt()
                remainingSeconds = (test.durationMinutes.coerceAtLeast(1) * 60 - elapsed).coerceAtLeast(0)
                if (remainingSeconds == 0) {
                    autoSubmitted = true
                    latestSubmit.value(latestAnswers.value.toMap())
                    break
                }
                delay(1000)
            }
        }
    }
    Column(Modifier.fillMaxSize()) {
        Row(Modifier.fillMaxWidth().padding(16.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) { Column { Text(test.subject.uppercase(), color = Teal, fontWeight = FontWeight.Bold, fontSize = 10.sp); Text(test.title, color = Ink, fontSize = 23.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold) }; Column(horizontalAlignment = Alignment.End) { Text("${remainingSeconds / 60}:${(remainingSeconds % 60).toString().padStart(2, '0')}", color = if (remainingSeconds < 60) Coral else Teal, fontWeight = FontWeight.Bold); TextButton(onClick = onExit, enabled = !busy) { Text("Close", color = Teal) } } }
        if (busy) SubmissionProgressPanel(submissionStage, submissionProgress, Modifier.padding(horizontal = 16.dp, vertical = 8.dp))
        LazyColumn(Modifier.weight(1f), contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 16.dp, vertical = 8.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
            item { Text("${questions.size} questions  ·  ${questions.sumOf { it.points }} points", color = Muted, fontSize = 12.sp) }
            items(questions, key = { it.id }) { question ->
                Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(14.dp)) {
                    Text("${question.points} points  ·  ${if (question.type == "mcq") "Choose one" else "Written response"}", color = Teal, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                    Text(question.prompt, color = Ink, fontSize = 15.sp, lineHeight = 21.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 6.dp, bottom = 8.dp))
                    if (question.type == "mcq") question.options.forEachIndexed { index, option ->
                        Row(Modifier.fillMaxWidth().clickable(enabled = !readOnly) { onAnswer(question.id, index.toString()) }.padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                            RadioButton(selected = answers[question.id] == index.toString(), enabled = !readOnly, onClick = { onAnswer(question.id, index.toString()) })
                            Text(option, color = Ink, fontSize = 13.sp)
                        }
                    } else OutlinedTextField(answers[question.id].orEmpty(), { onAnswer(question.id, it) }, readOnly = readOnly, label = { Text("Your answer") }, minLines = 3, modifier = Modifier.fillMaxWidth())
                }
            }
            item { Button(onClick = { onSubmit(answers) }, enabled = !busy && questions.isNotEmpty() && (readOnly || questions.all { !answers[it.id].isNullOrBlank() }), modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Teal)) { Text(if (busy) "Submitting..." else if (retryAvailable) "Retry mock analysis" else if (readOnly) "Retry AI analysis" else "Submit test") } }
        }
    }
}

@Composable
private fun SubmissionProgressPanel(stage: String, progress: Float, modifier: Modifier = Modifier) {
    Column(
        modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(10.dp)).padding(16.dp),
        verticalArrangement = Arrangement.spacedBy(10.dp)
    ) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(9.dp)) {
            if (progress < 1f) CircularProgressIndicator(color = Teal, strokeWidth = 2.dp, modifier = Modifier.width(22.dp).height(22.dp))
            else Icon(Icons.Default.AssignmentTurnedIn, contentDescription = null, tint = Teal)
            Column {
                Text(stage, color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
                Text(if (progress >= 1f) "Your analysis is ready" else "Your answers are being processed", color = Muted, fontSize = 11.sp)
            }
        }
        LinearProgressIndicator(
            progress = progress.coerceIn(0f, 1f),
            modifier = Modifier.fillMaxWidth().height(7.dp),
            color = Teal,
            trackColor = Color(0xFFE5ECEF)
        )
        Text("${(progress.coerceIn(0f, 1f) * 100).toInt()}%", color = Muted, fontSize = 10.sp, modifier = Modifier.align(Alignment.End))
    }
}

@Composable
private fun ResultPanel(result: JSONObject, mock: Boolean, onHome: () -> Unit) {
    val score = result.optDouble("score")
    val maxScore = result.optDouble("max_score")
    Column(Modifier.fillMaxSize()) {
        LazyColumn(
            Modifier.weight(1f).fillMaxWidth(),
            contentPadding = androidx.compose.foundation.layout.PaddingValues(horizontal = 18.dp, vertical = 20.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            item { Text(if (mock) "Practice complete" else "Test complete", color = Teal, fontSize = 10.sp, fontWeight = FontWeight.Bold) }
            item { Text("${score.toInt()} / ${maxScore.toInt()}", color = Ink, fontSize = 36.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.Bold) }
            if (result.has("test_rating")) item { Text("Test rating: ${result.optDouble("test_rating").toInt()} / 10", color = Teal, fontSize = 14.sp, fontWeight = FontWeight.Bold) }
            item { Text(result.optString("analysis"), color = Ink, fontSize = 14.sp, lineHeight = 20.sp) }
            item { Text("Advice", color = Teal, fontWeight = FontWeight.Bold) }
            item { Text(result.optString("advice"), color = Ink, fontSize = 13.sp, lineHeight = 19.sp) }
            result.optJSONArray("strengths")?.let { item { Text("Strengths: ${stringList(it).joinToString()}", color = Muted, fontSize = 12.sp) } }
            result.optJSONArray("focus_areas")?.let { item { Text("Focus next: ${stringList(it).joinToString()}", color = Muted, fontSize = 12.sp) } }
        }
        Surface(color = Color.White, shadowElevation = 6.dp) {
            Button(
                onClick = onHome,
                modifier = Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal = 18.dp, vertical = 12.dp).height(50.dp),
                colors = ButtonDefaults.buttonColors(containerColor = Teal),
                shape = RoundedCornerShape(9.dp)
            ) {
                Icon(Icons.Default.Home, contentDescription = null, tint = Color.White)
                Text("  Back to home", color = Color.White, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun AnalysisCard(analysis: TestAnalysis) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(14.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(analysis.subject, color = Teal, fontSize = 10.sp, fontWeight = FontWeight.Bold); Text("${analysis.score}/${analysis.maxScore}", color = Ink, fontWeight = FontWeight.Bold) }
        Text(analysis.title, color = Ink, fontSize = 17.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
        Text("${analysis.date}  ·  Test rating ${analysis.rating}/10", color = Muted, fontSize = 11.sp)
        Text(analysis.analysis, color = Ink, fontSize = 12.sp, modifier = Modifier.padding(top = 7.dp))
        Text(analysis.advice, color = Teal, fontSize = 12.sp, modifier = Modifier.padding(top = 6.dp))
    }
}

@Composable
private fun RatingCard(item: StudentRating, subjectFilter: String? = null, onClick: () -> Unit) {
    val subjectText = item.subjects.keys().asSequence()
        .filter { subjectFilter == null || it == subjectFilter }
        .map { "$it ${item.subjects.optDouble(it).let { rating -> String.format("%.1f", rating) }}/10" }
        .joinToString("  ·  ")
    val metricText = item.metrics.keys().asSequence()
        .map { item.metrics.optJSONObject(it)?.let { metric -> metric.optString("subject") to metric } }
        .filterNotNull()
        .filter { subjectFilter == null || it.first == subjectFilter }
        .joinToString("  ·  ") { (_, metric) -> "${metric.optString("name")} ${metric.optString("rating")}/10" }
    Column(Modifier.fillMaxWidth().clickable(onClick = onClick).background(Color.White, RoundedCornerShape(7.dp)).padding(13.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(item.name, color = Ink, fontWeight = FontWeight.SemiBold); if (subjectFilter == null) item.overall?.let { Text("Overall $it/10", color = Teal, fontSize = 11.sp, fontWeight = FontWeight.Bold) } }
        if (subjectFilter == null && !item.overallAnalysis.isNullOrBlank()) Text(item.overallAnalysis, color = Muted, fontSize = 11.sp, modifier = Modifier.padding(top = 5.dp))
        Text(subjectText, color = Muted, fontSize = 11.sp, modifier = Modifier.padding(top = 5.dp))
        if (metricText.isNotBlank()) Text(metricText, color = Teal, fontSize = 10.sp, modifier = Modifier.padding(top = 5.dp))
        Text("Open student analysis", color = Teal, fontSize = 11.sp, modifier = Modifier.padding(top = 5.dp))
    }
}

@Composable
private fun StudentProgressDashboard(report: JSONObject, student: StudentRating, isClassTeacher: Boolean) {
    val tests = report.optJSONArray("tests") ?: JSONArray()
    val subjectRatings = report.optJSONObject("subject_ratings") ?: JSONObject()
    val metricRatings = report.optJSONObject("metric_ratings") ?: JSONObject()
    val testSubjects = (0 until tests.length()).map { tests.getJSONObject(it).optString("subject") }.filter(String::isNotBlank)
    val subjectOptions = listOf("All subjects") + (subjectRatings.keys().asSequence().toList() + testSubjects).distinct().sorted()
    val allMetrics = metricRatings.keys().asSequence().mapNotNull { id ->
        metricRatings.optJSONObject(id)?.let { JSONObject().put("id", id).put("name", it.optString("name")).put("subject", it.optString("subject")) }
    }.toList()
    var selectedSubject by remember(student.id) { mutableStateOf("All subjects") }
    var selectedMeasure by remember(student.id) { mutableStateOf("Test rating") }
    var selectedMetricId by remember(student.id) { mutableStateOf("") }
    var selectedWindow by remember(student.id) { mutableStateOf("All assessments") }
    val visibleMetrics = allMetrics.filter { selectedSubject == "All subjects" || it.optString("subject") == selectedSubject }
    val selectedMetric = visibleMetrics.firstOrNull { it.optString("id") == selectedMetricId } ?: visibleMetrics.firstOrNull()
    val measures = buildList {
        add("Test rating")
        add("Subject rating")
        if (isClassTeacher) add("Overall rating")
        if (visibleMetrics.isNotEmpty()) add("Metric rating")
    }
    val activeMeasure = selectedMeasure.takeIf { it in measures } ?: measures.first()
    val filteredTests = (0 until tests.length()).map { tests.getJSONObject(it) }
        .filter { selectedSubject == "All subjects" || it.optString("subject") == selectedSubject }
        .sortedBy { it.optString("date") }
    val windowedTests = when (selectedWindow) {
        "Most recent 3" -> filteredTests.takeLast(3)
        "Most recent 6" -> filteredTests.takeLast(6)
        else -> filteredTests
    }
    val trend = windowedTests.mapNotNull { test ->
        val result = test.optJSONObject("result") ?: JSONObject()
        val rating = when (activeMeasure) {
            "Subject rating" -> result.optDouble("subject_rating", Double.NaN)
            "Overall rating" -> result.optDouble("overall_rating", Double.NaN)
            "Metric rating" -> {
                val metricArray = result.optJSONArray("metric_ratings") ?: JSONArray()
                (0 until metricArray.length()).firstNotNullOfOrNull { index ->
                    metricArray.getJSONObject(index).takeIf { it.optString("metric_id") == selectedMetric?.optString("id") }
                        ?.optDouble("rating", Double.NaN)?.takeUnless(Double::isNaN)
                } ?: Double.NaN
            }
            else -> result.optDouble("test_rating", Double.NaN)
        }
        if (rating.isNaN()) null else test.optString("date").takeLast(10) to rating.toFloat().coerceIn(0f, 10f)
    }
    val displayedSubjectRatings = subjectRatings.keys().asSequence()
        .filter { selectedSubject == "All subjects" || it == selectedSubject }
        .map { it to subjectRatings.optDouble(it).toFloat().coerceIn(0f, 10f) }
        .sortedBy { it.first }
        .toList()
    val latest = trend.lastOrNull()?.second
    val change = if (trend.size > 1) trend.last().second - trend.first().second else null

    Column(verticalArrangement = Arrangement.spacedBy(11.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.BarChart, contentDescription = null, tint = Teal)
            Text("  ${student.name}", color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 15.sp)
        }
        ChoiceDropdown("Subject", selectedSubject, subjectOptions) { selectedSubject = it }
        ChoiceDropdown("Rating series", activeMeasure, measures) { selectedMeasure = it }
        if (activeMeasure == "Metric rating" && selectedMetric != null) {
            ChoiceDropdown("Teacher metric", selectedMetric.optString("name"), visibleMetrics.map { it.optString("name") }) { name ->
                selectedMetricId = visibleMetrics.firstOrNull { it.optString("name") == name }?.optString("id").orEmpty()
            }
        }
        ChoiceDropdown("History window", selectedWindow, listOf("All assessments", "Most recent 6", "Most recent 3")) { selectedWindow = it }
        Row(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(8.dp)).padding(12.dp), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
            Column {
                Text("LATEST ${activeMeasure.uppercase()}", color = Muted, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                Text(latest?.let { String.format("%.1f / 10", it) } ?: "Not available", color = Ink, fontSize = 20.sp, fontWeight = FontWeight.Bold)
            }
            Column(horizontalAlignment = Alignment.End) {
                Text("CHANGE IN WINDOW", color = Muted, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                Text(change?.let { String.format("%+.1f points", it) } ?: "Need 2 results", color = if ((change ?: 0f) >= 0f) Teal else Coral, fontSize = 12.sp, fontWeight = FontWeight.SemiBold)
            }
        }
        RatingTrendChart(title = activeMeasure + if (activeMeasure == "Metric rating" && selectedMetric != null) " · ${selectedMetric.optString("name")}" else "", points = trend)
        SubjectRatingBars(displayedSubjectRatings)
    }
}

@Composable
private fun RatingTrendChart(title: String, points: List<Pair<String, Float>>) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(8.dp)).padding(13.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.ShowChart, contentDescription = null, tint = Teal)
            Text("  $title", color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        }
        Text("Rating out of 10", color = Muted, fontSize = 10.sp, modifier = Modifier.padding(top = 2.dp))
        if (points.isEmpty()) {
            BlankState("No ratings in this view", "Choose another subject, rating series, or history window.")
        } else {
            Text("Y-axis · Rating (0–10)", color = Muted, fontSize = 10.sp, fontWeight = FontWeight.Medium, modifier = Modifier.padding(top = 8.dp, start = 28.dp))
            Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
                Column(Modifier.height(180.dp).width(28.dp).padding(vertical = 5.dp), verticalArrangement = Arrangement.SpaceBetween) {
                    listOf("10", "7.5", "5", "2.5", "0").forEach { tick -> Text(tick, color = Muted, fontSize = 9.sp) }
                }
                Canvas(Modifier.weight(1f).height(180.dp)) {
                    val left = 8.dp.toPx()
                    val right = size.width - 8.dp.toPx()
                    val top = 8.dp.toPx()
                    val bottom = size.height - 8.dp.toPx()
                    for (step in 0..4) {
                        val y = bottom - (bottom - top) * step / 4f
                        drawLine(Color(0xFFE5ECEF), Offset(left, y), Offset(right, y), strokeWidth = 1.dp.toPx())
                    }
                    val coords = points.mapIndexed { index, point ->
                        val x = if (points.size == 1) (left + right) / 2 else left + (right - left) * index / (points.size - 1)
                        val y = bottom - (bottom - top) * point.second / 10f
                        Offset(x, y)
                    }
                    if (coords.size > 1) {
                        val path = Path().apply {
                            moveTo(coords.first().x, coords.first().y)
                            coords.drop(1).forEach { lineTo(it.x, it.y) }
                        }
                        drawPath(path, color = Teal, style = androidx.compose.ui.graphics.drawscope.Stroke(width = 3.dp.toPx()))
                    }
                    coords.forEach { drawCircle(color = Teal, radius = 4.dp.toPx(), center = it) }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                Text(points.first().first, color = Muted, fontSize = 9.sp)
                Text("${points.size} assessments", color = Muted, fontSize = 9.sp)
                Text(points.last().first, color = Muted, fontSize = 9.sp)
            }
            Text("X-axis · Assessment date", color = Muted, fontSize = 10.sp, fontWeight = FontWeight.Medium, modifier = Modifier.align(Alignment.CenterHorizontally))
        }
    }
}

@Composable
private fun SubjectRatingBars(subjects: List<Pair<String, Float>>) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(8.dp)).padding(13.dp), verticalArrangement = Arrangement.spacedBy(9.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Default.BarChart, contentDescription = null, tint = Teal)
            Text("  Subject ratings", color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
        }
        if (subjects.isEmpty()) {
            Text("No subject ratings available for this filter.", color = Muted, fontSize = 11.sp)
        } else subjects.forEach { (subject, rating) ->
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                Text(subject, color = Muted, fontSize = 10.sp, modifier = Modifier.width(98.dp))
                Box(Modifier.weight(1f).height(12.dp).background(Color(0xFFE8EFF0), RoundedCornerShape(6.dp))) {
                    Box(Modifier.fillMaxWidth((rating / 10f).coerceIn(0f, 1f)).height(12.dp).background(Teal, RoundedCornerShape(6.dp)))
                }
                Text(String.format("%.1f", rating), color = Ink, fontSize = 10.sp, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun ReviewAttemptDialog(title: String, payload: JSONObject, onDismiss: () -> Unit) {
    val paper = payload.optJSONArray("question_paper") ?: JSONArray()
    val attempts = payload.optJSONArray("attempts") ?: JSONArray()
    val selectedStudent = payload.optString("student_id")
    var selectedAttemptStudent by remember(selectedStudent, attempts.length()) {
        mutableStateOf(selectedStudent.ifBlank { if (attempts.length() > 0) attempts.getJSONObject(0).optString("student_id") else "" })
    }
    val selectedStudentAnswers = if (attempts.length() > 0) {
        val match = (0 until attempts.length()).firstOrNull { attempts.getJSONObject(it).optString("student_id") == selectedAttemptStudent }
        if (match != null) {
            attempts.getJSONObject(match).optJSONObject("answers") ?: JSONObject()
        } else {
            payload.optJSONObject("answers") ?: JSONObject()
        }
    } else payload.optJSONObject("answers") ?: JSONObject()
    val selectedAttempt = (0 until attempts.length()).map { attempts.getJSONObject(it) }
        .firstOrNull { it.optString("student_id") == selectedAttemptStudent }
    val selectedResult = selectedAttempt?.optJSONObject("result") ?: payload.optJSONObject("result")
    val selectedSubmittedAt = selectedAttempt?.optString("submitted_at") ?: payload.optString("submitted_at")
    val selectedStudentName = selectedAttempt?.optString("student_name")?.takeIf(String::isNotBlank)
        ?: selectedAttemptStudent
    AlertDialog(onDismissRequest = onDismiss, title = { Text(title, color = Ink, fontFamily = FontFamily.Serif) }, text = {
        LazyColumn(Modifier.height(520.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
            if (attempts.length() > 0) {
                item {
                    var studentMenuExpanded by remember { mutableStateOf(false) }
                    Column(verticalArrangement = Arrangement.spacedBy(5.dp)) {
                        Text("Select student copy", color = Muted, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
                        Box {
                            OutlinedButton(onClick = { studentMenuExpanded = true }, modifier = Modifier.fillMaxWidth()) {
                                Icon(Icons.Default.Person, contentDescription = null, tint = Teal)
                                Text("  $selectedStudentName", color = Ink, modifier = Modifier.weight(1f))
                                Icon(Icons.Default.ArrowDropDown, contentDescription = "Choose student", tint = Teal)
                            }
                            DropdownMenu(expanded = studentMenuExpanded, onDismissRequest = { studentMenuExpanded = false }) {
                                for (index in 0 until attempts.length()) {
                                    val attempt = attempts.getJSONObject(index)
                                    val studentId = attempt.optString("student_id")
                                    val displayName = attempt.optString("student_name").ifBlank { studentId }
                                    DropdownMenuItem(
                                        text = { Text(displayName, color = Ink) },
                                        leadingIcon = { Icon(Icons.Default.Person, contentDescription = null, tint = Teal) },
                                        trailingIcon = { if (studentId == selectedAttemptStudent) Icon(Icons.Default.AssignmentTurnedIn, contentDescription = "Selected", tint = Teal) },
                                        onClick = { selectedAttemptStudent = studentId; studentMenuExpanded = false }
                                    )
                                }
                            }
                        }
                    }
                }
            }
            item {
                Row(Modifier.fillMaxWidth().background(Panel, RoundedCornerShape(8.dp)).padding(10.dp), verticalAlignment = Alignment.CenterVertically) {
                    Icon(Icons.Default.Schedule, contentDescription = null, tint = Teal)
                    Text("  Submitted ${selectedSubmittedAt.ifBlank { "No submission date" }}", color = Muted, fontSize = 11.sp)
                }
            }
            selectedResult?.let { result ->
                item {
                    Column(Modifier.fillMaxWidth().background(Panel, RoundedCornerShape(10.dp)).padding(12.dp)) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Default.AssignmentTurnedIn, contentDescription = null, tint = Teal)
                            Text("  ${selectedStudentName}'s result", color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 12.sp)
                        }
                        Text("Score ${result.optString("score")}/${result.optString("max_score")} · ${result.optString("test_rating")}/10", color = Teal, fontWeight = FontWeight.Bold, fontSize = 12.sp)
                        Text(result.optString("analysis"), color = Ink, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
                        if (result.optString("advice").isNotBlank()) {
                            Row(Modifier.padding(top = 6.dp), verticalAlignment = Alignment.Top) {
                                Icon(Icons.Default.TipsAndUpdates, contentDescription = null, tint = Teal)
                                Text("  ${result.optString("advice")}", color = Muted, fontSize = 11.sp)
                            }
                        }
                    }
                }
            }
            for (index in 0 until paper.length()) {
                val question = paper.getJSONObject(index)
                item {
                    Column(Modifier.fillMaxWidth().background(Panel, RoundedCornerShape(10.dp)).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                        Text("Q${index + 1} · ${question.optString("question_type").uppercase()}", color = Teal, fontSize = 10.sp, fontWeight = FontWeight.Bold)
                        Text(question.optString("prompt"), color = Ink, fontSize = 13.sp, fontWeight = FontWeight.SemiBold)
                        val options = question.optJSONArray("options") ?: JSONArray()
                        val answerValue = selectedStudentAnswers.opt(question.optString("id"))
                        if (options.length() > 0) {
                            for (optionIndex in 0 until options.length()) {
                                val selected = answerValue.toString() == optionIndex.toString()
                                Text("${('A' + optionIndex).toString()} ${options.getString(optionIndex)}" + if (selected) "  • Selected" else "", color = if (selected) Teal else Ink, fontSize = 11.sp)
                            }
                        } else {
                            Text("Student answer: ${answerValue ?: question.optString("student_answer")}", color = Ink, fontSize = 11.sp)
                        }
                        if (question.has("answer_key")) {
                            Text("Answer key: ${question.opt("answer_key")}", color = Muted, fontSize = 10.sp)
                        }
                    }
                }
            }
        }
    }, confirmButton = { TextButton(onClick = onDismiss) { Text("Close", color = Teal) } })
}

@Composable
private fun AnalysisDialog(report: JSONObject, student: StudentRating, isClassTeacher: Boolean, onSearch: (String, String?) -> Unit, onDismiss: () -> Unit) {
    val context = LocalContext.current
    val overall = report.optJSONObject("overall")
    val tests = report.optJSONArray("tests") ?: JSONArray()
    val subjectRatings = report.optJSONObject("subject_ratings") ?: JSONObject()
    val availableSubjects = subjectRatings.keys().asSequence().toList().sorted()
    var asOf by remember(student.id) { mutableStateOf("") }
    var selectedSubject by remember(student.id, isClassTeacher) { mutableStateOf(if (isClassTeacher) "" else availableSubjects.firstOrNull().orEmpty()) }
    var selectedTestId by remember(student.id) { mutableStateOf("") }
    val allTests = (0 until tests.length()).map { tests.getJSONObject(it) }
    val subjectTests = allTests.filter { selectedSubject.isNotBlank() && it.optString("subject") == selectedSubject }
    val selectedTest = subjectTests.firstOrNull { it.optString("test_id") == selectedTestId } ?: subjectTests.firstOrNull()
    AlertDialog(onDismissRequest = onDismiss, title = { Text(student.name, color = Ink, fontFamily = FontFamily.Serif) }, text = {
        LazyColumn(Modifier.height(420.dp), verticalArrangement = Arrangement.spacedBy(8.dp)) {
            item { Text("As of ${report.optString("as_of", "latest")}", color = Muted, fontSize = 11.sp) }
            item {
                Row(verticalAlignment = Alignment.CenterVertically) {
                    OutlinedButton(onClick = {
                        val today = Calendar.getInstance()
                        DatePickerDialog(
                            context,
                            { _, year, month, day ->
                                asOf = String.format("%04d-%02d-%02d", year, month + 1, day)
                                onSearch(asOf, selectedSubject.takeIf(String::isNotBlank))
                            },
                            today.get(Calendar.YEAR), today.get(Calendar.MONTH), today.get(Calendar.DAY_OF_MONTH)
                        ).show()
                    }, modifier = Modifier.fillMaxWidth()) { Text(asOf.ifBlank { "Choose history date" }, color = Teal) }
                }
            }
            if (isClassTeacher && overall != null) item {
                Text("Current overall state · ${overall.optString("rating")}/10", color = Teal, fontWeight = FontWeight.Bold)
                Text(overall.optString("analysis"), color = Ink, fontSize = 12.sp)
                val overallAdvice = allTests.firstOrNull()?.optJSONObject("result")?.optString("advice").orEmpty()
                if (overallAdvice.isNotBlank()) Text("Advice: $overallAdvice", color = Muted, fontSize = 12.sp)
            }
            if (availableSubjects.isNotEmpty()) item {
                ChoiceDropdown("Subject results", selectedSubject.ifBlank { "Select subject" }, availableSubjects) {
                    selectedSubject = it
                    selectedTestId = ""
                }
            }
            if (selectedSubject.isNotBlank()) {
                val subjectRating = subjectRatings.optDouble(selectedSubject, Double.NaN)
                val subjectNarrative = (report.optJSONObject("subject_analyses") ?: JSONObject()).optJSONObject(selectedSubject)
                val selectedMetricRatings = (report.optJSONObject("metric_ratings") ?: JSONObject()).let { metrics ->
                    metrics.keys().asSequence().mapNotNull { key -> metrics.optJSONObject(key)?.let { key to it } }
                        .filter { it.second.optString("subject") == selectedSubject }
                }
                if (!subjectRating.isNaN()) item { Text("$selectedSubject rating · ${String.format("%.1f", subjectRating)}/10", color = Teal, fontWeight = FontWeight.Bold) }
                subjectNarrative?.let { narrative ->
                    item { Text("Subject analysis", color = Teal, fontWeight = FontWeight.Bold) }
                    item { Text(narrative.optString("analysis"), color = Ink, fontSize = 12.sp) }
                    item { Text("Advice: ${narrative.optString("advice")}", color = Muted, fontSize = 12.sp) }
                }
                selectedMetricRatings.forEach { (_, metric) -> item { Text("${metric.optString("name")} · ${metric.optString("rating")}/10", color = Muted, fontSize = 11.sp) } }
                if (subjectTests.isEmpty()) item { BlankState("No tests for this subject", "No analyzed test history is available for this subject on this date.") }
                else {
                    item { ChoiceDropdown("Test history", selectedTest?.optString("title").orEmpty(), subjectTests.map { it.optString("title") }) { title -> selectedTestId = subjectTests.firstOrNull { it.optString("title") == title }?.optString("test_id").orEmpty() } }
                    selectedTest?.let { test ->
                        val result = test.optJSONObject("result") ?: JSONObject()
                        item {
                            Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(6.dp)).padding(12.dp), verticalArrangement = Arrangement.spacedBy(6.dp)) {
                                Text("${test.optString("date")} · ${result.optString("score")}/${result.optString("max_score")} · ${result.optString("test_rating")}/10", color = Teal, fontWeight = FontWeight.Bold, fontSize = 11.sp)
                                Text(result.optString("analysis"), color = Ink, fontSize = 12.sp)
                                Text("Advice: ${result.optString("advice")}", color = Muted, fontSize = 12.sp)
                            }
                        }
                    }
                }
            } else if (!isClassTeacher) {
                item { BlankState("No subject access", "This teacher has no subject assignment in the selected class.") }
            }
        }
    }, confirmButton = { TextButton(onClick = onDismiss) { Text("Close", color = Teal) } })
}

@Composable
private fun TestBuilderDialog(existingTest: DigitalTest?, initialQuestions: List<DraftQuestion>, subjects: List<String>, onDismiss: () -> Unit, onPublish: (DigitalTest?, String, String, String, String, Int, List<DraftQuestion>) -> Unit) {
    val context = LocalContext.current
    var title by remember(existingTest?.id) { mutableStateOf(existingTest?.title.orEmpty()) }
    var subject by remember(existingTest?.id, subjects) { mutableStateOf(existingTest?.subject ?: subjects.firstOrNull() ?: "Mathematics") }
    var date by remember(existingTest?.id) { mutableStateOf(existingTest?.dueDate?.takeIf(String::isNotBlank) ?: Calendar.getInstance().let { String.format("%04d-%02d-%02d", it.get(Calendar.YEAR), it.get(Calendar.MONTH) + 1, it.get(Calendar.DAY_OF_MONTH)) }) }
    var duration by remember(existingTest?.id) { mutableStateOf((existingTest?.durationMinutes ?: 45).toString()) }
    var prompt by remember { mutableStateOf("") }
    var points by remember { mutableStateOf("2") }
    var type by remember { mutableStateOf("mcq") }
    var options by remember { mutableStateOf("") }
    var answerKey by remember { mutableStateOf("") }
    val draft = remember(existingTest?.id) { mutableStateListOf<DraftQuestion>().apply { addAll(initialQuestions) } }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(if (existingTest == null) "Build digital test" else "Edit digital test", color = Ink, fontFamily = FontFamily.Serif) }, text = {
        LazyColumn(Modifier.height(520.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            item { OutlinedTextField(title, { title = it }, label = { Text("Test title") }, singleLine = true) }
            item { ChoiceDropdown("Subject", subject, subjects.ifEmpty { listOf(subject) }) { subject = it } }
            item { OutlinedButton(onClick = {
                val calendar = Calendar.getInstance()
                DatePickerDialog(context, { _, year, month, day -> date = String.format("%04d-%02d-%02d", year, month + 1, day) }, calendar.get(Calendar.YEAR), calendar.get(Calendar.MONTH), calendar.get(Calendar.DAY_OF_MONTH)).show()
            }, modifier = Modifier.fillMaxWidth()) { Text("Due date · $date") } }
            item { OutlinedTextField(duration, { duration = it.filter(Char::isDigit).take(3) }, label = { Text("Time limit (minutes, 1-240)") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number), singleLine = true) }
            item { Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) { TextButton(onClick = { type = "mcq" }) { Text(if (type == "mcq") "• MCQ" else "MCQ", color = Teal) }; TextButton(onClick = { type = "subjective" }) { Text(if (type == "subjective") "• Written" else "Written", color = Teal) } } }
            item { OutlinedTextField(prompt, { prompt = it }, label = { Text("Question") }, minLines = 2) }
            item { OutlinedTextField(points, { points = it.filter { char -> char.isDigit() || char == '.' } }, label = { Text("Points") }, keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Decimal), singleLine = true) }
            if (type == "mcq") {
                item { OutlinedTextField(options, { options = it }, label = { Text("Options, one per line") }, minLines = 3) }
                item { OutlinedTextField(answerKey, { answerKey = it.filter(Char::isDigit) }, label = { Text("Correct option number (starting at 1)") }, singleLine = true) }
            } else item { OutlinedTextField(answerKey, { answerKey = it }, label = { Text("Answer key / grading rubric") }, minLines = 3) }
            item { OutlinedButton(onClick = {
                val choices = if (type == "mcq") options.lines().map(String::trim).filter(String::isNotEmpty) else emptyList()
                val key: Any? = if (type == "mcq") answerKey.toIntOrNull()?.minus(1)?.takeIf { it in choices.indices } else answerKey.takeIf(String::isNotBlank)
                if (prompt.isNotBlank() && points.toDoubleOrNull() != null && key != null && (type != "mcq" || choices.size >= 2)) {
                    draft.add(DraftQuestion(prompt.trim(), points.toDouble(), type, choices, key))
                    prompt = ""; options = ""; answerKey = ""
                }
            }, modifier = Modifier.fillMaxWidth()) { Text("Add question (${draft.size})") } }
            items(draft) { Text("${draft.size}. ${it.type.uppercase()} · ${it.prompt}", color = Muted, fontSize = 11.sp) }
        }
    }, confirmButton = { TextButton(onClick = { duration.toIntOrNull()?.takeIf { it in 1..240 }?.let { minutes -> if (title.isNotBlank() && subject.isNotBlank() && draft.isNotEmpty()) onPublish(existingTest, title, subject, "Assessment", date, minutes, draft.toList()) } }) { Text(if (existingTest == null) "Publish" else "Save changes", color = Teal) } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = Muted) } })
}

@Composable
private fun AdminDialog(mode: String, classes: List<SchoolClass>, subjects: List<String>, editingUser: JSONObject?, onDismiss: () -> Unit, onSave: (JSONObject) -> Unit) {
    var username by remember(mode, editingUser?.optString("id")) { mutableStateOf(editingUser?.optString("id").orEmpty()) }
    var name by remember(mode, editingUser?.optString("name")) { mutableStateOf(editingUser?.optString("name").orEmpty()) }
    var password by remember { mutableStateOf("") }
    var newUsername by remember { mutableStateOf("") }
    var classId by remember(mode, editingUser?.optString("class_id")) { mutableStateOf(editingUser?.optString("class_id")?.takeIf(String::isNotBlank) ?: classes.firstOrNull()?.id.orEmpty()) }
    var assignmentClassId by remember(mode, editingUser?.optString("id")) { mutableStateOf(classes.firstOrNull()?.id.orEmpty()) }
    var assignmentSubject by remember(mode, subjects) { mutableStateOf(subjects.firstOrNull().orEmpty()) }
    var assignmentClassTeacher by remember(mode, editingUser?.optString("id")) { mutableStateOf(false) }
    val assignmentRows = remember(mode, editingUser?.optString("id")) {
        mutableStateListOf<JSONObject>().apply {
            val existing = editingUser?.optJSONArray("assignments") ?: JSONArray()
            for (index in 0 until existing.length()) add(existing.getJSONObject(index))
        }
    }
    val editingTeacher = mode == "update" && editingUser?.optString("role") == "teacher"
    val title = when (mode) { "student" -> "Add student"; "teacher" -> "Add teacher"; else -> "Edit ${editingUser?.optString("role") ?: "profile"}" }
    AlertDialog(onDismissRequest = onDismiss, title = { Text(title, color = Ink, fontFamily = FontFamily.Serif) }, text = {
        LazyColumn(Modifier.height(440.dp), verticalArrangement = Arrangement.spacedBy(7.dp)) {
            item { OutlinedTextField(username, { username = it }, label = { Text(if (mode == "update") "Username" else "Username") }, singleLine = true, enabled = mode != "update") }
            item { OutlinedTextField(name, { name = it }, label = { Text("Full name") }, singleLine = true) }
            if (mode == "update") item { OutlinedTextField(newUsername, { newUsername = it }, label = { Text("New username (optional)") }, singleLine = true) }
            item { OutlinedTextField(password, { password = it }, label = { Text(if (mode == "update") "New password (optional)" else "Password (10+ characters)") }, singleLine = true, visualTransformation = PasswordVisualTransformation()) }
            if (mode == "student") item {
                ChoiceDropdown("Class", classes.firstOrNull { it.id == classId }?.name ?: "Select class", classes.map { it.name }) { selected -> classId = classes.firstOrNull { it.name == selected }?.id.orEmpty() }
            }
            if (mode == "teacher" || editingTeacher) {
                item { Heading("Teaching assignments", "PROFILE ACCESS") }
                item { ChoiceDropdown("Class", classes.firstOrNull { it.id == assignmentClassId }?.name ?: "Select class", classes.map { it.name }) { selected -> assignmentClassId = classes.firstOrNull { it.name == selected }?.id.orEmpty() } }
                item {
                    Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                        TextButton(onClick = { assignmentClassTeacher = false }) { Text(if (!assignmentClassTeacher) "• Subject teacher" else "Subject teacher", color = Teal) }
                        TextButton(onClick = { assignmentClassTeacher = true }) { Text(if (assignmentClassTeacher) "• Class teacher" else "Class teacher", color = Teal) }
                    }
                }
                if (!assignmentClassTeacher) item { ChoiceDropdown("Subject", assignmentSubject.ifBlank { "Select subject" }, subjects, { assignmentSubject = it }) }
                item {
                    TextButton(onClick = {
                        val assignmentType = if (assignmentClassTeacher) "class" else "subject"
                        val assignmentValue = if (assignmentClassTeacher) JSONObject.NULL else assignmentSubject
                        val exists = assignmentRows.any { it.optString("class_id") == assignmentClassId && it.optString("assignment_type") == assignmentType && it.optString("subject") == if (assignmentValue === JSONObject.NULL) "" else assignmentSubject }
                        if (assignmentClassId.isNotBlank() && (assignmentClassTeacher || assignmentSubject.isNotBlank()) && !exists) {
                            assignmentRows.add(JSONObject().put("class_id", assignmentClassId).put("assignment_type", assignmentType).put("subject", assignmentValue))
                        }
                    }) { Text("Add assignment", color = Teal) }
                }
                items(assignmentRows.size) { index ->
                    val assignment = assignmentRows[index]
                    val className = classes.firstOrNull { it.id == assignment.optString("class_id") }?.name ?: assignment.optString("class_name")
                    val label = if (assignment.optString("assignment_type") == "class") "$className · Class teacher" else "$className · ${assignment.optString("subject")}"
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.CenterVertically) {
                        Text(label, color = Ink, fontSize = 12.sp, modifier = Modifier.weight(1f))
                        TextButton(onClick = { assignmentRows.removeAt(index) }) { Text("Remove", color = Coral) }
                    }
                }
            }
        }
    }, confirmButton = { TextButton(onClick = {
        val assignments = JSONArray()
        assignmentRows.forEach { assignment ->
            assignments.put(JSONObject().put("teacher_id", username).put("class_id", assignment.getString("class_id")).put("assignment_type", assignment.getString("assignment_type")).put("subject", assignment.opt("subject") ?: JSONObject.NULL))
        }
        if (mode == "student" && username.isNotBlank() && name.isNotBlank() && password.length >= 10 && classId.isNotBlank()) onSave(JSONObject().put("username", username).put("name", name).put("password", password).put("class_id", classId))
        if (mode == "teacher" && username.isNotBlank() && name.isNotBlank() && password.length >= 10 && assignmentRows.isNotEmpty()) onSave(JSONObject().put("username", username).put("name", name).put("password", password).put("assignments", assignments))
        if (mode == "update" && username.isNotBlank() && name.isNotBlank() && (password.isBlank() || password.length >= 10)) {
            val form = JSONObject().put("id", username).put("name", name).put("new_username", newUsername).put("password", password).put("class_id", if (editingUser?.optString("role") == "student") classId else "")
            if (editingTeacher) form.put("assignments", assignments)
            onSave(form)
        }
    }) { Text("Save", color = Teal) } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = Muted) } })
}

@Composable
private fun MetricDialog(subjects: List<String>, onDismiss: () -> Unit, onSave: (String, String, String) -> Unit) {
    var subject by remember { mutableStateOf(subjects.firstOrNull() ?: "Mathematics") }
    var name by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Add subject metric", color = Ink) }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
            ChoiceDropdown("Subject", subject, subjects.ifEmpty { listOf(subject) }) { subject = it }
            OutlinedTextField(name, { name = it }, label = { Text("Metric name") }, singleLine = true)
            OutlinedTextField(description, { description = it }, label = { Text("What should the AI rate?") }, minLines = 2)
        }
    }, confirmButton = { TextButton(onClick = { if (name.isNotBlank()) onSave(subject, name, description) }) { Text("Save metric", color = Teal) } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = Muted) } })
}

@Composable
private fun ActionButton(label: String, onClick: () -> Unit) {
    Button(onClick = onClick, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Teal), shape = RoundedCornerShape(5.dp)) { Text(label, color = Color.White) }
}

@Composable
private fun ProfileDetails(user: SignedInUser, classes: List<SchoolClass>) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(6.dp)).padding(16.dp), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Text(user.name, color = Ink, fontSize = 20.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
        Text("${if (user.isAdmin) "Administrator" else user.role.replaceFirstChar(Char::uppercase)} · ${user.username}", color = Muted, fontSize = 12.sp)
        if (classes.isEmpty()) Text("No class assignments", color = Muted, fontSize = 12.sp)
        if (!user.isAdmin) classes.forEach { schoolClass ->
            val assignment = when {
                user.role == "student" -> "Student · ${schoolClass.name}"
                schoolClass.isClassTeacher -> "${schoolClass.name} · Class teacher"
                schoolClass.subjects.isNotEmpty() -> "${schoolClass.name} · ${schoolClass.subjects.joinToString() }"
                else -> schoolClass.name
            }
            Text(assignment, color = Teal, fontSize = 12.sp)
        }
    }
}

@Composable
private fun BlankState(title: String, message: String) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(6.dp)).padding(16.dp)) { Text(title, color = Ink, fontWeight = FontWeight.SemiBold); Text(message, color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp)) }
}

private fun parseTests(array: JSONArray): List<DigitalTest> = (0 until array.length()).map { index ->
    val item = array.getJSONObject(index)
    DigitalTest(item.getString("id"), item.getString("title"), item.getString("subject"), item.optString("kind"), item.optString("due_date"), item.optInt("question_count"), item.optBoolean("is_mock"), item.optBoolean("completed"), item.optBoolean("pending"), item.optInt("duration_minutes", 60), item.optInt("students_taken"))
}

private fun parseQuestions(array: JSONArray): List<DigitalQuestion> = (0 until array.length()).map { index ->
    val item = array.getJSONObject(index)
    val options = item.optJSONArray("options") ?: JSONArray()
    DigitalQuestion(item.getString("id"), item.getString("prompt"), item.optDouble("points", 1.0), item.optString("question_type", "subjective"), (0 until options.length()).map { options.getString(it) })
}

private fun parseDraftQuestions(array: JSONArray): List<DraftQuestion> = (0 until array.length()).map { index ->
    val item = array.getJSONObject(index)
    val options = item.optJSONArray("options") ?: JSONArray()
    DraftQuestion(item.getString("prompt"), item.optDouble("points", 1.0), item.optString("question_type", "subjective"), (0 until options.length()).map { options.getString(it) }, item.opt("answer_key") ?: "")
}

private fun parseAnalyses(array: JSONArray): List<TestAnalysis> = (0 until array.length()).map { index ->
    val item = array.getJSONObject(index)
    TestAnalysis(item.getString("test_id"), item.optString("title"), item.optString("subject"), item.optString("date"), item.optString("score"), item.optString("max_score"), item.optString("test_rating"), item.optString("analysis"), item.optString("advice"), stringList(item.optJSONArray("strengths")), stringList(item.optJSONArray("focus_areas")))
}

private fun parseRatings(array: JSONArray): List<StudentRating> = (0 until array.length()).map { index ->
    val item = array.getJSONObject(index)
    StudentRating(item.getString("student_id"), item.optString("name"), if (item.isNull("overall_rating")) null else item.optString("overall_rating"), item.optString("overall_analysis").takeIf(String::isNotBlank), item.optJSONObject("subject_ratings") ?: JSONObject(), item.optJSONObject("metric_ratings") ?: JSONObject(), item.optString("as_of").takeIf(String::isNotBlank))
}

private fun stringList(array: JSONArray?): List<String> = if (array == null) emptyList() else (0 until array.length()).map { array.optString(it) }.filter(String::isNotBlank)
private fun jsonSummary(json: JSONObject): String = json.keys().asSequence().map { "$it ${json.opt(it)}" }.joinToString(" · ")
