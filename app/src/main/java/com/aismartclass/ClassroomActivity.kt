package com.aismartclass

import android.app.DatePickerDialog
import android.content.Context
import android.os.Bundle
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
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
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
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
private val Ink = Color(0xFF172B2A)
private val Muted = Color(0xFF71817C)
private val Paper = Color(0xFFF6F7F1)
private val Green = Color(0xFFB9E5C8)
private val Teal = Color(0xFF176B5B)
private val Coral = Color(0xFFF2A78F)

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
    var questions by remember { mutableStateOf<List<DigitalQuestion>>(emptyList()) }
    var result by remember { mutableStateOf<JSONObject?>(null) }
    var report by remember { mutableStateOf<JSONObject?>(null) }
    var reportStudent by remember { mutableStateOf<StudentRating?>(null) }
    var reportIsClassTeacher by remember { mutableStateOf(false) }
    var showBuilder by remember { mutableStateOf(false) }
    var editingTest by remember { mutableStateOf<DigitalTest?>(null) }
    var editingQuestions by remember { mutableStateOf(emptyList<DraftQuestion>()) }
    var showAdminDialog by remember { mutableStateOf<String?>(null) }
    var showMetricDialog by remember { mutableStateOf(false) }
    val tests = remember { mutableStateListOf<DigitalTest>() }
    val analyses = remember { mutableStateListOf<TestAnalysis>() }
    val ratings = remember { mutableStateListOf<StudentRating>() }
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
            result = null
        }
    }
    fun submitExam(current: SignedInUser, selected: DigitalTest, currentAnswers: Map<String, String>) = perform("Could not submit test") {
        val answerJson = JSONObject()
        questions.forEach { question ->
            val value = currentAnswers[question.id].orEmpty()
            if (question.type == "mcq") answerJson.put(question.id, value.toIntOrNull() ?: JSONObject.NULL) else answerJson.put(question.id, value)
        }
        val api = SmartclassApi(backendUrl, current.token)
        val response = try {
            api.submitTest(selected.id, answerJson, selected.isMock)
        } catch (failure: Exception) {
            if (!selected.isMock) {
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
            }
            throw failure
        }
        if (!selected.isMock) refresh(current, selectedClassId)
        activity.runOnUiThread {
            result = response
            savedAttemptPending = false
        }
    }
    fun openStudentReport(item: StudentRating, current: SignedInUser, asOf: String? = null, subject: String? = null) = perform("Could not open student analysis") {
        val response = SmartclassApi(backendUrl, current.token).studentAnalysis(selectedClassId, item.id, asOf, subject)
        val isClassTeacher = current.isAdmin || current.classes.firstOrNull { it.id == selectedClassId }?.isClassTeacher == true
        activity.runOnUiThread { reportStudent = item; report = response; reportIsClassTeacher = isClassTeacher }
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
                    busy = busy,
                    startedAtMillis = examStartedAtMillis,
                    onAnswer = { id, value -> answers[id] = value },
                    onSubmit = { currentAnswers -> submitExam(current, exam!!, currentAnswers) },
                    onExit = { exam = null; questions = emptyList(); answers.clear(); savedAttemptPending = false }
                )
                result != null -> ResultPanel(result!!, exam?.isMock == true, onDone = {
                    result = null; exam = null; questions = emptyList(); answers.clear(); savedAttemptPending = false; page = if (student) "Results" else "Tests"
                })
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
                    onClass = { selectedClassId = it; val selected = current.classes.firstOrNull { item -> item.id == it }; if (selected != null) perform("Could not refresh class") { refresh(current, selected.id) } },
                    onPage = { page = it },
                    onLogout = { user = null; tests.clear(); analyses.clear(); ratings.clear() },
                    onOpenTest = { openExam(it, current) },
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
    Column(Modifier.fillMaxSize().padding(26.dp), verticalArrangement = Arrangement.Center) {
        Text("AI SMARTCLASS  /  SCHOOL PORTAL", color = Teal, fontWeight = FontWeight.Bold, fontSize = 11.sp)
        Text("Your classroom,", color = Ink, fontSize = 34.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
        Text("ready when you are.", color = Ink, fontSize = 34.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
        Text("Sign in to view your class work.", color = Muted, modifier = Modifier.padding(top = 8.dp, bottom = 20.dp))
        OutlinedTextField(username, { username = it }, label = { Text("Username") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(password, { password = it }, label = { Text("Password") }, singleLine = true, visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
        Button(onClick = { onLogin(username.trim(), password) }, enabled = !busy && username.isNotBlank(), colors = ButtonDefaults.buttonColors(containerColor = Teal), modifier = Modifier.fillMaxWidth().padding(top = 15.dp)) { if (busy) CircularProgressIndicator() else Text("Sign in") }
    }
}

@Composable
private fun PortalPanel(
    user: SignedInUser, activeClass: SchoolClass?, classes: List<SchoolClass>, page: String, busy: Boolean,
    tests: List<DigitalTest>, analyses: List<TestAnalysis>, ratings: List<StudentRating>, metrics: List<JSONObject>, adminUsers: List<JSONObject>,
    onClass: (String) -> Unit, onPage: (String) -> Unit, onLogout: () -> Unit,
    onOpenTest: (DigitalTest) -> Unit, onOpenBuilder: () -> Unit, onEditTest: (DigitalTest) -> Unit, onDeleteTest: (DigitalTest) -> Unit,
    onReport: (StudentRating, String?) -> Unit, onAddStudent: () -> Unit, onAddTeacher: () -> Unit,
    onEditUser: (JSONObject) -> Unit, onDeleteUser: (JSONObject) -> Unit, onCreateMetric: () -> Unit
) {
    val admin = user.isAdmin
    val teacher = user.role == "teacher" && !admin
    val navItems = if (admin) listOf("Admin", "Profile") else if (teacher) listOf("Tests", "Class", "Metrics", "Profile") else listOf("Tests", "Results", "Mock", "Profile")
    var testSubject by remember(user.id, activeClass?.id) { mutableStateOf("") }
    var resultSubject by remember(user.id, activeClass?.id) { mutableStateOf("") }
    var mockSubject by remember(user.id, activeClass?.id) { mutableStateOf("") }
    var classSubject by remember(user.id, activeClass?.id) { mutableStateOf("") }
    var adminClassFilter by remember(user.id) { mutableStateOf("All classes") }
    var adminRoleFilter by remember(user.id) { mutableStateOf("All roles") }
    var pendingDeleteUser by remember { mutableStateOf<JSONObject?>(null) }
    var pendingDeleteTest by remember { mutableStateOf<DigitalTest?>(null) }
    fun classLabel(item: SchoolClass) = if (teacher && item.isClassTeacher) "${item.name} (Class Teacher)" else item.name
    Column(Modifier.fillMaxSize()) {
        LazyColumn(Modifier.weight(1f), contentPadding = androidx.compose.foundation.layout.PaddingValues(18.dp), verticalArrangement = Arrangement.spacedBy(13.dp)) {
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
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp), modifier = Modifier.fillMaxWidth()) { navItems.forEach { item -> TextButton(onClick = { onPage(item) }) { Text(if (item == page) "• $item" else item, color = if (item == page) Teal else Muted, fontWeight = if (item == page) FontWeight.Bold else FontWeight.Normal) } } }
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
                    items(filtered, key = { it.id }) { test -> TestCard(test, teacher || admin, onOpenTest, onEditTest, { pendingDeleteTest = it }) }
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
private fun TestCard(test: DigitalTest, teacher: Boolean, onOpen: (DigitalTest) -> Unit, onEdit: (DigitalTest) -> Unit, onDelete: (DigitalTest) -> Unit) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(15.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(test.subject.uppercase(), color = Teal, fontSize = 10.sp, fontWeight = FontWeight.Bold); Text(if (test.isMock) "MOCK" else test.dueDate, color = Muted, fontSize = 10.sp) }
        Text(test.title, color = Ink, fontSize = 18.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 5.dp))
        Text("${test.questionCount} questions  ·  ${test.kind}", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 3.dp, bottom = 10.dp))
        if (teacher) {
            Text("${test.studentsTaken} students have attempted this test", color = Muted, fontSize = 11.sp)
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                if (test.studentsTaken == 0 && !test.isMock) TextButton(onClick = { onEdit(test) }) { Text("Edit", color = Teal) }
                if (!test.isMock) TextButton(onClick = { onDelete(test) }) { Text("Delete", color = Coral) }
            }
        } else {
            val action = when { test.isMock -> "Try mock test"; test.pending -> "Retry AI analysis"; test.completed -> "Completed"; else -> "Start test" }
            Button(onClick = { onOpen(test) }, enabled = test.isMock || !test.completed, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Teal), shape = RoundedCornerShape(5.dp)) { Text(action, color = Color.White) }
        }
    }
}

@Composable
private fun ExamPanel(test: DigitalTest, questions: List<DigitalQuestion>, answers: Map<String, String>, readOnly: Boolean, busy: Boolean, startedAtMillis: Long, onAnswer: (String, String) -> Unit, onSubmit: (Map<String, String>) -> Unit, onExit: () -> Unit) {
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
        if (busy) Row(Modifier.fillMaxWidth().padding(horizontal = 16.dp, vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) { CircularProgressIndicator(color = Teal, strokeWidth = 2.dp, modifier = Modifier.width(18.dp).height(18.dp)); Text("  Submitting answers and preparing your result...", color = Muted, fontSize = 12.sp) }
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
            item { Button(onClick = { onSubmit(answers) }, enabled = !busy && questions.isNotEmpty() && (readOnly || questions.all { !answers[it.id].isNullOrBlank() }), modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Teal)) { Text(if (busy) "Submitting..." else if (readOnly) "Retry AI analysis" else "Submit test") } }
        }
    }
}

@Composable
private fun ResultPanel(result: JSONObject, mock: Boolean, onDone: () -> Unit) {
    val score = result.optDouble("score")
    val maxScore = result.optDouble("max_score")
    Column(Modifier.fillMaxSize().padding(18.dp), verticalArrangement = Arrangement.spacedBy(12.dp)) {
        Text(if (mock) "Practice complete" else "Test complete", color = Teal, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        Text("${score.toInt()} / ${maxScore.toInt()}", color = Ink, fontSize = 36.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.Bold)
        if (result.has("test_rating")) Text("Test rating: ${result.optDouble("test_rating").toInt()} / 10", color = Teal, fontSize = 14.sp, fontWeight = FontWeight.Bold)
        Text(result.optString("analysis"), color = Ink, fontSize = 14.sp, lineHeight = 20.sp)
        Text("Advice", color = Teal, fontWeight = FontWeight.Bold)
        Text(result.optString("advice"), color = Ink, fontSize = 13.sp, lineHeight = 19.sp)
        result.optJSONArray("strengths")?.let { Text("Strengths: ${stringList(it).joinToString()}", color = Muted, fontSize = 12.sp) }
        result.optJSONArray("focus_areas")?.let { Text("Focus next: ${stringList(it).joinToString()}", color = Muted, fontSize = 12.sp) }
        Spacer(Modifier.height(4.dp))
        ActionButton("Done", onDone)
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
