package com.aismartclass

import android.content.Context
import android.content.Intent
import android.database.Cursor
import android.net.Uri
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.FileProvider
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors

private const val ClassroomLog = "AIClassroom"
private val ClassroomInk = Color(0xFF172B2A)
private val ClassroomMuted = Color(0xFF71817C)
private val ClassroomPaper = Color(0xFFF6F7F1)
private val ClassroomGreen = Color(0xFFB9E5C8)
private val ClassroomTeal = Color(0xFF176B5B)
private val ClassroomCoral = Color(0xFFF2A78F)

private data class LoggedInUser(val id: String, val name: String, val username: String, val role: String, val token: String, val classId: String, val className: String)
private data class PublishedTest(val id: String, val title: String, val subject: String, val kind: String, val dueDate: String, val questions: Int, val hasPaper: Boolean)
private data class StudentWork(val id: String, val testId: String, val title: String, val status: String, val score: String?, val maxScore: String?, val feedback: List<String>, val teacherAdvice: String, val studentName: String?)
private data class WeeklyTarget(val title: String, val target: String, val week: String)

class ClassroomActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { ClassroomApp(this) }
    }
}

@Composable
private fun ClassroomApp(context: Context) {
    val activity = context as ComponentActivity
    val preferences = remember { context.getSharedPreferences("smartclass", Context.MODE_PRIVATE) }
    val executor = remember { Executors.newSingleThreadExecutor() }
    var backendUrl by remember { mutableStateOf(preferences.getString("backend_url", "http://10.0.2.2:8000") ?: "http://10.0.2.2:8000") }
    var session by remember { mutableStateOf<LoggedInUser?>(null) }
    var loading by remember { mutableStateOf(false) }
    var errorTitle by remember { mutableStateOf("Something went wrong") }
    var errorMessage by remember { mutableStateOf<String?>(null) }
    var activePage by remember { mutableStateOf("Home") }
    var showCreateTest by remember { mutableStateOf(false) }
    var showCreatePlan by remember { mutableStateOf(false) }
    var selectedAdvice by remember { mutableStateOf<StudentWork?>(null) }
    var pendingTestId by remember { mutableStateOf<String?>(null) }
    val tests = remember { mutableStateListOf<PublishedTest>() }
    val submissions = remember { mutableStateListOf<StudentWork>() }
    val plans = remember { mutableStateListOf<WeeklyTarget>() }

    val showError: (String, String) -> Unit = { title, message ->
        errorTitle = title
        errorMessage = message
    }
    val execute: (String, () -> Unit) -> Unit = { actionName, work ->
        if (!loading) {
            loading = true
            executor.execute {
                try {
                    work()
                } catch (exception: Exception) {
                    Log.e(ClassroomLog, "$actionName failed", exception)
                    activity.runOnUiThread {
                        showError(actionName, exception.message ?: "Please check your connection and try again.")
                    }
                } finally {
                    activity.runOnUiThread { loading = false }
                }
            }
        }
    }

    fun refreshDashboard(api: SmartclassApi, user: LoggedInUser) {
        val freshTests = parseTests(api.tests(user.classId))
        val freshSubmissions = parseSubmissions(api.submissions(user.classId, user.role == "teacher"))
        val freshPlans = if (user.role == "teacher") parsePlans(api.plans(user.classId)) else emptyList()
        activity.runOnUiThread {
            tests.clear()
            tests.addAll(freshTests)
            submissions.clear()
            submissions.addAll(freshSubmissions)
            plans.clear()
            plans.addAll(freshPlans)
        }
    }

    val answerSheetPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) {
            Log.i(ClassroomLog, "Student cancelled answer-sheet selection")
            pendingTestId = null
        } else {
            val currentUser = session
            val testId = pendingTestId
            if (currentUser == null || testId == null) {
                showError("Submission unavailable", "Sign in again and select the test before uploading a PDF.")
            } else {
                pendingTestId = null
                execute("Answer-sheet submission failed") {
                    val filename = contentName(context, uri)
                    val pdfBytes = readPdf(context, uri)
                    val api = SmartclassApi(backendUrl, currentUser.token)
                    val submitted = api.uploadAnswerSheet(testId, filename, pdfBytes)
                    val submissionId = submitted.getString("id")
                    try {
                        api.evaluate(submissionId)
                        refreshDashboard(api, currentUser)
                        activity.runOnUiThread { showError("AI review ready", "Your answer sheet has been graded. Open My work to see your score and advice.") }
                    } catch (exception: Exception) {
                        Log.e(ClassroomLog, "AI evaluation failed after submission was stored", exception)
                        activity.runOnUiThread { showError("Submitted, grading failed", exception.message ?: "Your PDF was saved, but AI evaluation did not finish.") }
                        refreshDashboard(api, currentUser)
                    }
                }
            }
        }
    }

    val questionPaperPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        if (uri == null) {
            Log.i(ClassroomLog, "Teacher cancelled question-paper selection")
            pendingTestId = null
        } else {
            val currentUser = session
            val testId = pendingTestId
            if (currentUser == null || testId == null) {
                showError("Publishing unavailable", "Sign in again before uploading a test paper.")
            } else {
                pendingTestId = null
                execute("Question-paper upload failed") {
                    val filename = contentName(context, uri)
                    val pdfBytes = readPdf(context, uri)
                    val api = SmartclassApi(backendUrl, currentUser.token)
                    api.uploadTestPaper(testId, filename, pdfBytes)
                    refreshDashboard(api, currentUser)
                    activity.runOnUiThread { showError("Test published", "The question paper is now available to students in ${currentUser.className}.") }
                }
            }
        }
    }

    MaterialTheme {
        Surface(color = ClassroomPaper, modifier = Modifier.fillMaxSize()) {
            if (session == null) {
                LoginScreen(
                    backendUrl = backendUrl,
                    onBackendUrlChange = { backendUrl = it },
                    loading = loading,
                    onLogin = { username, password ->
                        preferences.edit().putString("backend_url", backendUrl.trim().trimEnd('/')).apply()
                        execute("Sign-in failed") {
                            val response = SmartclassApi(backendUrl).login(username, password)
                            val userJson = response.getJSONObject("user")
                            val classJson = response.getJSONObject("class")
                            val loggedIn = LoggedInUser(
                                userJson.getString("id"), userJson.getString("name"), userJson.getString("username"),
                                userJson.getString("role"), response.getString("access_token"),
                                classJson.getString("id"), classJson.getString("name")
                            )
                            refreshDashboard(SmartclassApi(backendUrl, loggedIn.token), loggedIn)
                            activity.runOnUiThread { session = loggedIn; activePage = "Home" }
                        }
                    }
                )
            } else {
                PortalScreen(
                    user = session!!,
                    activePage = activePage,
                    loading = loading,
                    tests = tests,
                    submissions = submissions,
                    plans = plans,
                    onPage = { activePage = it },
                    onLogout = { session = null; activePage = "Home" },
                    onUploadQuestionPaper = { test ->
                        pendingTestId = test.id
                        questionPaperPicker.launch(arrayOf("application/pdf"))
                    },
                    onSubmitAnswers = { test ->
                        pendingTestId = test.id
                        answerSheetPicker.launch(arrayOf("application/pdf"))
                    },
                    onOpenPaper = { testId, title ->
                        val currentUser = session ?: return@PortalScreen
                        execute("Couldn't open question paper") {
                            val bytes = SmartclassApi(backendUrl, currentUser.token).download("/api/tests/$testId/paper")
                            openPdf(context, "$title-question-paper.pdf", bytes)
                        }
                    },
                    onOpenAnswer = { work ->
                        val currentUser = session ?: return@PortalScreen
                        execute("Couldn't open answer sheet") {
                            val bytes = SmartclassApi(backendUrl, currentUser.token).download("/api/submissions/${work.id}/answer")
                            openPdf(context, "${work.title}-answer-sheet.pdf", bytes)
                        }
                    },
                    onShowAdvice = { selectedAdvice = it },
                    onRetryEvaluation = { work ->
                        val currentUser = session ?: return@PortalScreen
                        execute("AI review failed") {
                            SmartclassApi(backendUrl, currentUser.token).evaluate(work.id)
                            refreshDashboard(SmartclassApi(backendUrl, currentUser.token), currentUser)
                        }
                    },
                    onAddPlanClick = { showCreatePlan = true },
                    onAddTestClick = { showCreateTest = true }
                )
            }
        }
    }

    if (showCreateTest) CreateTestDialog(
        onDismiss = { showCreateTest = false },
        onPublish = { title, subject, kind, dueDate ->
            val currentUser = session ?: return@CreateTestDialog
            execute("Couldn't create test") {
                val api = SmartclassApi(backendUrl, currentUser.token)
                val created = api.createTest(currentUser.classId, title, subject, kind, dueDate)
                refreshDashboard(api, currentUser)
                activity.runOnUiThread {
                    pendingTestId = created.getString("id")
                    showCreateTest = false
                    questionPaperPicker.launch(arrayOf("application/pdf"))
                }
            }
        }
    )
    if (showCreatePlan) CreatePlanDialog(
        onDismiss = { showCreatePlan = false },
        onCreate = { title, target ->
            val currentUser = session ?: return@CreatePlanDialog
            execute("Couldn't save weekly target") {
                SmartclassApi(backendUrl, currentUser.token).createPlan(currentUser.classId, "WEEK 04", title, target)
                refreshDashboard(SmartclassApi(backendUrl, currentUser.token), currentUser)
                activity.runOnUiThread { showCreatePlan = false }
            }
        }
    )
    selectedAdvice?.let { work -> AdviceDialog(work, session?.role == "teacher") { selectedAdvice = null } }
    errorMessage?.let { message ->
        AlertDialog(
            onDismissRequest = { errorMessage = null },
            title = { Text(errorTitle, color = ClassroomInk) },
            text = { Text(message, color = ClassroomMuted) },
            confirmButton = { TextButton(onClick = { errorMessage = null }) { Text("OK", color = ClassroomTeal) } }
        )
    }
}

@Composable
private fun LoginScreen(backendUrl: String, onBackendUrlChange: (String) -> Unit, loading: Boolean, onLogin: (String, String) -> Unit) {
    var username by remember { mutableStateOf("") }
    var password by remember { mutableStateOf("") }
    Column(Modifier.fillMaxSize().padding(horizontal = 26.dp), verticalArrangement = Arrangement.Center) {
        Text("AI SMARTCLASS  /  CLASS 09", color = ClassroomTeal, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
        Text("Welcome back.", color = ClassroomInk, fontSize = 34.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 8.dp))
        Text("Sign in to your class portal.", color = ClassroomMuted, fontSize = 14.sp, modifier = Modifier.padding(top = 5.dp, bottom = 22.dp))
        OutlinedTextField(username, { username = it }, label = { Text("Username") }, singleLine = true, modifier = Modifier.fillMaxWidth())
        OutlinedTextField(password, { password = it }, label = { Text("Password") }, singleLine = true, visualTransformation = PasswordVisualTransformation(), keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Password), modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
        OutlinedTextField(backendUrl, onBackendUrlChange, label = { Text("Backend address") }, singleLine = true, modifier = Modifier.fillMaxWidth().padding(top = 8.dp))
        Text("On your phone, use your computer's Wi-Fi IP (for example, http://192.168.1.20:8000). Demo password: yasir123123", color = ClassroomMuted, fontSize = 11.sp, lineHeight = 16.sp, modifier = Modifier.padding(top = 9.dp))
        Button(onClick = { onLogin(username.trim(), password) }, enabled = !loading && username.isNotBlank() && password.isNotBlank(), colors = ButtonDefaults.buttonColors(containerColor = ClassroomTeal), shape = RoundedCornerShape(5.dp), modifier = Modifier.fillMaxWidth().padding(top = 18.dp)) {
            if (loading) CircularProgressIndicator(color = Color.White, strokeWidth = 2.dp, modifier = Modifier.size(18.dp)) else Text("Sign in", color = Color.White)
        }
        Text("Student: naruto or sasuke     Teacher: kakashi", color = ClassroomMuted, fontSize = 11.sp, modifier = Modifier.align(Alignment.CenterHorizontally).padding(top = 15.dp))
    }
}

@Composable
private fun PortalScreen(
    user: LoggedInUser,
    activePage: String,
    loading: Boolean,
    tests: List<PublishedTest>,
    submissions: List<StudentWork>,
    plans: List<WeeklyTarget>,
    onPage: (String) -> Unit,
    onLogout: () -> Unit,
    onUploadQuestionPaper: (PublishedTest) -> Unit,
    onSubmitAnswers: (PublishedTest) -> Unit,
    onOpenPaper: (String, String) -> Unit,
    onOpenAnswer: (StudentWork) -> Unit,
    onShowAdvice: (StudentWork) -> Unit,
    onRetryEvaluation: (StudentWork) -> Unit,
    onAddPlanClick: () -> Unit,
    onAddTestClick: () -> Unit
) {
    val teacher = user.role == "teacher"
    Column(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 18.dp),
            verticalArrangement = Arrangement.spacedBy(15.dp)
        ) {
            item {
                Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
                    Column(Modifier.weight(1f)) {
                        Text("AI SMARTCLASS  /  ${user.className.uppercase()}", color = ClassroomTeal, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                        Text("${if (teacher) "Teacher" else "Student"} portal", color = ClassroomInk, fontSize = 27.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
                    }
                    TextButton(onClick = onLogout) { Text("Sign out", color = ClassroomTeal) }
                }
            }
            item {
                Row(horizontalArrangement = Arrangement.spacedBy(7.dp), modifier = Modifier.fillMaxWidth()) {
                    PortalTab("Home", activePage, onPage)
                    PortalTab("Tests", activePage, onPage)
                    PortalTab(if (teacher) "Reviews" else "My work", activePage, onPage)
                    if (teacher) PortalTab("Plans", activePage, onPage)
                }
            }
            if (loading) item { Row(verticalAlignment = Alignment.CenterVertically) { CircularProgressIndicator(color = ClassroomTeal, strokeWidth = 2.dp, modifier = Modifier.size(18.dp)); Text("  Working with your class...", color = ClassroomMuted, fontSize = 12.sp) } }
            when (activePage) {
                "Tests" -> {
                    item { SectionTitle(if (teacher) "Class tests" else "Tests for your class", if (teacher) "PUBLISHED TO ${user.className.uppercase()}" else "ASSIGNED TO YOU") }
                    if (teacher) item { PrimaryAction("＋  Create test and upload PDF", onAddTestClick) }
                    if (tests.isEmpty()) item { EmptyPortalState("No tests published", "Published tests for this class will appear here.") }
                    items(tests, key = { it.id }) { test ->
                        TestCard(test, teacher, submissions.any { it.testId == test.id }, onOpenPaper, onUploadQuestionPaper, onSubmitAnswers)
                    }
                }
                "Reviews", "My work" -> {
                    item { SectionTitle(if (teacher) "Student submissions" else "Your submissions", if (teacher) "CLASS REVIEW" else "FEEDBACK & FILES") }
                    if (submissions.isEmpty()) item { EmptyPortalState("No submissions yet", "Submitted answer sheets and AI feedback appear here.") }
                    items(submissions, key = { it.id }) { work ->
                        WorkCard(work, teacher, onOpenPaper, onOpenAnswer, onShowAdvice, onRetryEvaluation)
                    }
                }
                "Plans" -> {
                    item { SectionTitle("Weekly targets", "CLASS PLAN") }
                    item { PrimaryAction("＋  Add a weekly target", onAddPlanClick) }
                    if (plans.isEmpty()) item { EmptyPortalState("No targets set", "Add a weekly learning target for the class.") }
                    items(plans) { PlanLine(it) }
                }
                else -> {
                    item {
                        Column(Modifier.fillMaxWidth().background(ClassroomInk, RoundedCornerShape(7.dp)).padding(18.dp)) {
                            Text(if (teacher) "YOUR CLASS, AT A GLANCE" else "YOUR LEARNING, IN FOCUS", color = ClassroomGreen, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                            Text(if (teacher) "Small steps.\nStronger outcomes." else "Steady progress\nbeats cramming.", color = Color.White, fontSize = 25.sp, lineHeight = 29.sp, fontFamily = FontFamily.Serif, modifier = Modifier.padding(top = 8.dp))
                            Text(if (teacher) "${tests.size} published tests  ·  ${submissions.size} submissions" else "${tests.size} class tests  ·  ${submissions.size} submissions", color = ClassroomGreen, fontSize = 12.sp, modifier = Modifier.padding(top = 12.dp))
                        }
                    }
                    item { SectionTitle(if (teacher) "Classroom activity" else "Next up", if (teacher) "YOUR CLASS" else "CLASS 09") }
                    if (teacher) {
                        item { PrimaryAction("＋  Upload a question paper") { onAddTestClick() } }
                        items(tests.take(2), key = { it.id }) { test -> TestCard(test, true, false, onOpenPaper, onUploadQuestionPaper, onSubmitAnswers) }
                    } else {
                        items(tests.take(2), key = { it.id }) { test -> TestCard(test, false, submissions.any { it.testId == test.id }, onOpenPaper, onUploadQuestionPaper, onSubmitAnswers) }
                        if (submissions.isNotEmpty()) item { SectionTitle("Latest feedback", "YOUR WORK") }
                        items(submissions.take(2), key = { it.id }) { work -> WorkCard(work, false, onOpenPaper, onOpenAnswer, onShowAdvice, onRetryEvaluation) }
                    }
                }
            }
        }
        Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 8.dp, vertical = 8.dp), horizontalArrangement = Arrangement.SpaceAround) {
            listOf("Home", "Tests", if (teacher) "Reviews" else "My work").forEach { PortalTabBottom(it, activePage, onPage) }
            if (teacher) PortalTabBottom("Plans", activePage, onPage)
        }
    }
}

@Composable
private fun PortalTab(label: String, selected: String, onPage: (String) -> Unit) {
    Surface(onClick = { onPage(label) }, color = if (selected == label) ClassroomTeal else Color.White, shape = RoundedCornerShape(16.dp)) {
        Text(label, color = if (selected == label) Color.White else ClassroomMuted, fontSize = 10.sp, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(horizontal = 10.dp, vertical = 7.dp))
    }
}

@Composable
private fun PortalTabBottom(label: String, selected: String, onPage: (String) -> Unit) {
    Column(Modifier.clickable { onPage(label) }.padding(horizontal = 8.dp, vertical = 3.dp), horizontalAlignment = Alignment.CenterHorizontally) {
        Text(when (label) { "Home" -> "⌂"; "Tests" -> "▣"; "Reviews", "My work" -> "▤"; else -> "⌁" }, color = if (selected == label) ClassroomTeal else ClassroomMuted, fontSize = 18.sp)
        Text(label, color = if (selected == label) ClassroomTeal else ClassroomMuted, fontSize = 9.sp, fontWeight = if (selected == label) FontWeight.Bold else FontWeight.Normal)
    }
}

@Composable
private fun SectionTitle(title: String, eyebrow: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
        Text(title, color = ClassroomInk, fontSize = 20.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
        Text(eyebrow, color = ClassroomMuted, fontSize = 8.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp, modifier = Modifier.padding(bottom = 3.dp))
    }
}

@Composable
private fun TestCard(test: PublishedTest, teacher: Boolean, submitted: Boolean, onOpenPaper: (String, String) -> Unit, onUploadQuestionPaper: (PublishedTest) -> Unit, onSubmitAnswers: (PublishedTest) -> Unit) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(14.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
            Text(test.kind.uppercase(), color = ClassroomTeal, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
            Text(test.dueDate, color = ClassroomMuted, fontSize = 10.sp)
        }
        Text(test.title, color = ClassroomInk, fontSize = 17.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 4.dp))
        Text("${test.subject}  ·  ${test.questions} questions", color = ClassroomMuted, fontSize = 11.sp, modifier = Modifier.padding(top = 3.dp, bottom = 10.dp))
        Row(horizontalArrangement = Arrangement.spacedBy(7.dp), verticalAlignment = Alignment.CenterVertically) {
            if (test.hasPaper) OutlinedButton(onClick = { onOpenPaper(test.id, test.title) }, shape = RoundedCornerShape(5.dp)) { Text("View paper", color = ClassroomTeal, fontSize = 11.sp) }
            if (teacher && !test.hasPaper) OutlinedButton(onClick = { onUploadQuestionPaper(test) }, shape = RoundedCornerShape(5.dp)) { Text("Upload PDF", color = ClassroomTeal, fontSize = 11.sp) }
            if (!teacher && test.hasPaper) Button(onClick = { onSubmitAnswers(test) }, enabled = !submitted, colors = ButtonDefaults.buttonColors(containerColor = ClassroomTeal), shape = RoundedCornerShape(5.dp)) { Text(if (submitted) "Submitted" else "Submit answers", fontSize = 11.sp) }
        }
    }
}

@Composable
private fun WorkCard(work: StudentWork, teacher: Boolean, onOpenPaper: (String, String) -> Unit, onOpenAnswer: (StudentWork) -> Unit, onShowAdvice: (StudentWork) -> Unit, onRetryEvaluation: (StudentWork) -> Unit) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(14.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween) {
            Column(Modifier.weight(1f)) {
                Text(work.title, color = ClassroomInk, fontSize = 15.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
                if (teacher && work.studentName != null) Text(work.studentName, color = ClassroomMuted, fontSize = 11.sp, modifier = Modifier.padding(top = 2.dp))
            }
            Text(work.score?.let { "$it / ${work.maxScore ?: "?"}" } ?: work.status.replaceFirstChar { it.uppercase() }, color = ClassroomTeal, fontSize = 10.sp, fontWeight = FontWeight.Bold)
        }
        Row(horizontalArrangement = Arrangement.spacedBy(4.dp), modifier = Modifier.padding(top = 7.dp)) {
            TextButton(onClick = { onOpenPaper(work.testId, work.title) }) { Text("Question paper", color = ClassroomTeal, fontSize = 10.sp) }
            TextButton(onClick = { onOpenAnswer(work) }) { Text("${if (teacher) "Student's" else "My"} answer", color = ClassroomTeal, fontSize = 10.sp) }
            TextButton(onClick = { onShowAdvice(work) }, enabled = work.feedback.isNotEmpty() || work.teacherAdvice.isNotBlank()) { Text("AI advice", color = ClassroomTeal, fontSize = 10.sp) }
            if (work.score == null) TextButton(onClick = { onRetryEvaluation(work) }) { Text("Retry AI", color = ClassroomTeal, fontSize = 10.sp) }
        }
    }
}

@Composable
private fun PlanLine(plan: WeeklyTarget) {
    Row(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(6.dp)).padding(13.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(34.dp).background(ClassroomGreen, RoundedCornerShape(5.dp)), contentAlignment = Alignment.Center) { Text("↗", color = ClassroomTeal, fontWeight = FontWeight.Bold) }
        Column(Modifier.weight(1f).padding(horizontal = 11.dp)) {
            Text(plan.title, color = ClassroomInk, fontWeight = FontWeight.SemiBold, fontSize = 13.sp)
            Text(plan.target, color = ClassroomMuted, fontSize = 11.sp)
        }
        Text(plan.week, color = ClassroomTeal, fontSize = 8.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun PrimaryAction(label: String, onClick: () -> Unit) {
    Button(onClick = onClick, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = ClassroomTeal), shape = RoundedCornerShape(5.dp)) { Text(label, color = Color.White) }
}

@Composable
private fun EmptyPortalState(title: String, detail: String) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(16.dp)) {
        Text(title, color = ClassroomInk, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
        Text(detail, color = ClassroomMuted, fontSize = 11.sp, modifier = Modifier.padding(top = 4.dp))
    }
}

@Composable
private fun CreateTestDialog(onDismiss: () -> Unit, onPublish: (String, String, String, String) -> Unit) {
    var title by remember { mutableStateOf("") }
    var subject by remember { mutableStateOf("Mathematics") }
    var kind by remember { mutableStateOf("Lecture test") }
    var dueDate by remember { mutableStateOf("Fri, 17 Oct") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Publish a class test", color = ClassroomInk, fontFamily = FontFamily.Serif) },
        text = {
            Column(verticalArrangement = Arrangement.spacedBy(7.dp)) {
                OutlinedTextField(title, { title = it }, label = { Text("Test title") }, singleLine = true)
                OutlinedTextField(subject, { subject = it }, label = { Text("Subject") }, singleLine = true)
                Row(horizontalArrangement = Arrangement.spacedBy(5.dp)) {
                    listOf("Lecture test", "Cumulative").forEach { type -> TextButton(onClick = { kind = type }) { Text(if (kind == type) "• $type" else type, color = ClassroomTeal, fontSize = 10.sp) } }
                }
                OutlinedTextField(dueDate, { dueDate = it }, label = { Text("Due date") }, singleLine = true)
                Text("Next, choose the question-paper PDF. Students in this class will see the published test.", color = ClassroomMuted, fontSize = 11.sp)
            }
        },
        confirmButton = { TextButton(onClick = { if (title.isNotBlank()) onPublish(title, subject, kind, dueDate) }) { Text("Choose PDF", color = ClassroomTeal) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = ClassroomMuted) } }
    )
}

@Composable
private fun CreatePlanDialog(onDismiss: () -> Unit, onCreate: (String, String) -> Unit) {
    var title by remember { mutableStateOf("") }
    var target by remember { mutableStateOf("") }
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text("Weekly target", color = ClassroomInk, fontFamily = FontFamily.Serif) },
        text = { Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(title, { title = it }, label = { Text("Focus area") }, singleLine = true)
            OutlinedTextField(target, { target = it }, label = { Text("Measurable target") }, minLines = 2)
        } },
        confirmButton = { TextButton(onClick = { if (title.isNotBlank() && target.isNotBlank()) onCreate(title, target) }) { Text("Save", color = ClassroomTeal) } },
        dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = ClassroomMuted) } }
    )
}

@Composable
private fun AdviceDialog(work: StudentWork, teacher: Boolean, onDismiss: () -> Unit) {
    AlertDialog(
        onDismissRequest = onDismiss,
        title = { Text(if (work.score != null) "AI feedback  ·  ${work.score}/${work.maxScore}" else "AI feedback", color = ClassroomInk, fontFamily = FontFamily.Serif) },
        text = { LazyColumn(verticalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.height(300.dp)) {
            if (work.feedback.isEmpty() && work.teacherAdvice.isBlank()) item { Text("Feedback is not available yet.", color = ClassroomMuted) }
            items(work.feedback) { Text("• $it", color = ClassroomInk, fontSize = 12.sp) }
            if (teacher && work.teacherAdvice.isNotBlank()) item {
                Column(Modifier.fillMaxWidth().background(ClassroomPaper, RoundedCornerShape(5.dp)).padding(10.dp)) {
                    Text("FOR THE TEACHER", color = ClassroomTeal, fontSize = 9.sp, fontWeight = FontWeight.Bold)
                    Text(work.teacherAdvice, color = ClassroomInk, fontSize = 12.sp, modifier = Modifier.padding(top = 5.dp))
                }
            }
        } },
        confirmButton = { TextButton(onClick = onDismiss) { Text("Close", color = ClassroomTeal) } }
    )
}

private fun parseTests(array: JSONArray): List<PublishedTest> = (0 until array.length()).map { index ->
    val item = array.getJSONObject(index)
    PublishedTest(item.getString("id"), item.getString("title"), item.getString("subject"), item.getString("kind"), item.optString("due_date"), item.optInt("question_count"), item.optBoolean("has_paper"))
}

private fun parsePlans(array: JSONArray): List<WeeklyTarget> = (0 until array.length()).map { index ->
    val item = array.getJSONObject(index)
    WeeklyTarget(item.getString("title"), item.getString("target"), item.getString("week"))
}

private fun parseSubmissions(array: JSONArray): List<StudentWork> = (0 until array.length()).map { index ->
    val item = array.getJSONObject(index)
    val feedbackValue = item.optJSONArray("feedback")
    val feedback = if (feedbackValue == null) emptyList() else (0 until feedbackValue.length()).map { feedbackIndex ->
        val entry = feedbackValue.opt(feedbackIndex)
        if (entry is JSONObject) listOf("question", "error", "advice", "improvement").mapNotNull { key -> entry.optString(key).takeIf(String::isNotBlank) }.joinToString(" ")
        else entry.toString()
    }.filter(String::isNotBlank)
    StudentWork(item.getString("id"), item.getString("test_id"), item.getString("title"), item.optString("status", "submitted"), if (item.isNull("score")) null else item.optString("score"), if (item.isNull("max_score")) null else item.optString("max_score"), feedback, item.optString("teacher_advice"), item.optString("student_name").takeIf(String::isNotBlank))
}

private fun contentName(context: Context, uri: Uri): String = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor: Cursor ->
    val column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
    if (cursor.moveToFirst() && column >= 0) cursor.getString(column) else null
} ?: "answer-sheet.pdf"

private fun readPdf(context: Context, uri: Uri): ByteArray {
    val bytes = context.contentResolver.openInputStream(uri)?.use { it.readBytes() } ?: throw IllegalArgumentException("Could not read the selected PDF")
    if (bytes.size > 50 * 1024 * 1024) throw IllegalArgumentException("PDF is larger than the 50 MB testing limit")
    if (!bytes.take(5).toByteArray().contentEquals("%PDF-".toByteArray())) throw IllegalArgumentException("Choose a valid PDF file")
    return bytes
}

private fun openPdf(context: Context, filename: String, bytes: ByteArray) {
    val file = File(context.cacheDir, filename.replace(Regex("[^A-Za-z0-9._-]"), "_"))
    file.writeBytes(bytes)
    val uri = FileProvider.getUriForFile(context, "${context.packageName}.files", file)
    val intent = Intent(Intent.ACTION_VIEW).apply {
        setDataAndType(uri, "application/pdf")
        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
    }
    context.startActivity(intent)
}
