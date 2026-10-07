package com.aismartclass

import android.content.Context
import android.database.Cursor
import android.os.Bundle
import android.provider.OpenableColumns
import android.util.Log
import androidx.activity.ComponentActivity
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Canvas
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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.Divider
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
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import org.json.JSONArray
import org.json.JSONObject

private val Ink = Color(0xFF172B2A)
private val Muted = Color(0xFF71817C)
private val Paper = Color(0xFFF6F7F1)
private val Green = Color(0xFFB9E5C8)
private val Teal = Color(0xFF176B5B)
private val Coral = Color(0xFFF2A78F)
private val Yellow = Color(0xFFF0D775)
private val Line = Color(0xFFE2E8DF)
private const val LogTag = "AIClassroom"

private data class ClassTest(val title: String, val subject: String, val kind: String, val date: String, val questions: Int)
private data class StudyPlan(val title: String, val detail: String, val week: String)
private data class Submission(val test: String, val file: String, val status: String)

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent { SmartclassApp(this) }
    }
}

@Composable
private fun SmartclassApp(context: Context) {
    val prefs = remember { context.getSharedPreferences("smartclass", Context.MODE_PRIVATE) }
    val tests = remember { mutableStateListOf<ClassTest>().apply { addAll(loadTests(prefs)) } }
    val plans = remember { mutableStateListOf<StudyPlan>().apply { addAll(loadPlans(prefs)) } }
    val submissions = remember { mutableStateListOf<Submission>().apply { addAll(loadSubmissions(prefs)) } }
    var teacher by remember { mutableStateOf(false) }
    var page by remember { mutableStateOf("Home") }
    var showTestDialog by remember { mutableStateOf(false) }
    var showPlanDialog by remember { mutableStateOf(false) }
    var uploadTest by remember { mutableStateOf<ClassTest?>(null) }
    var errorTitle by remember { mutableStateOf("Something went wrong") }
    var errorMessage by remember { mutableStateOf<String?>(null) }

    val pdfPicker = rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri ->
        val selectedTest = uploadTest
        if (uri == null) {
            Log.i(LogTag, "Answer-sheet file selection cancelled")
            uploadTest = null
        } else if (selectedTest == null) {
            Log.e(LogTag, "Received a PDF selection without an active test")
        } else {
            try {
                context.contentResolver.takePersistableUriPermission(uri, android.content.Intent.FLAG_GRANT_READ_URI_PERMISSION)
                val name = context.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor: Cursor ->
                    val column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                    if (cursor.moveToFirst() && column >= 0) cursor.getString(column) else null
                } ?: "Answer sheet PDF"
                submissions.add(0, Submission(selectedTest.title, name, "Submitted for review"))
                saveSubmissions(prefs, submissions)
                Log.i(LogTag, "PDF selected and saved to the local submission list")
                uploadTest = null
            } catch (exception: Exception) {
                Log.e(LogTag, "Could not process the selected answer-sheet PDF", exception)
                errorTitle = "PDF selection failed"
                errorMessage = "The PDF could not be saved. Please choose the file again."
            }
        }
    }
    val startPdfSelection: (ClassTest) -> Unit = { test ->
        uploadTest = test
        try {
            pdfPicker.launch(arrayOf("application/pdf"))
        } catch (exception: Exception) {
            Log.e(LogTag, "Could not open the PDF picker", exception)
            errorTitle = "PDF selection failed"
            errorMessage = "The PDF picker could not be opened. Please try again."
        }
    }

    MaterialTheme {
        Surface(color = Paper, modifier = Modifier.fillMaxSize()) {
            Column(Modifier.fillMaxSize()) {
                LazyColumn(
                    modifier = Modifier.weight(1f),
                    contentPadding = androidx.compose.foundation.layout.PaddingValues(start = 20.dp, end = 20.dp, top = 20.dp, bottom = 18.dp),
                    verticalArrangement = Arrangement.spacedBy(18.dp)
                ) {
                    item {
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                            Column {
                                Text("FIELDNOTES  /  CLASS 08", color = Teal, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                                Text(if (teacher) "Teacher space" else "Good morning, Aanya", color = Ink, fontSize = 29.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
                            }
                            Box(Modifier.size(44.dp).background(if (teacher) Coral else Green, CircleShape), contentAlignment = Alignment.Center) {
                                Text(if (teacher) "MR" else "AS", color = Ink, fontWeight = FontWeight.Bold)
                            }
                        }
                    }
                    item {
                        Row(horizontalArrangement = Arrangement.spacedBy(8.dp), modifier = Modifier.fillMaxWidth()) {
                            RoleChip("Student", !teacher) { teacher = false }
                            RoleChip("Teacher", teacher) { teacher = true }
                            Spacer(Modifier.weight(1f))
                            Text("2025 / 26  ▾", color = Muted, fontSize = 12.sp, modifier = Modifier.align(Alignment.CenterVertically))
                        }
                    }
                    item {
                        Card(colors = CardDefaults.cardColors(containerColor = Ink), shape = RoundedCornerShape(8.dp), modifier = Modifier.fillMaxWidth()) {
                            Column(Modifier.padding(20.dp)) {
                                Text(if (teacher) "YOUR CLASS, AT A GLANCE" else "YOUR LEARNING, IN FOCUS", color = Green, fontSize = 10.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                                Spacer(Modifier.height(8.dp))
                                Text(if (teacher) "Small steps.\nStronger outcomes." else "Steady progress\nbeats cramming.", color = Color.White, fontSize = 25.sp, lineHeight = 29.sp, fontFamily = FontFamily.Serif)
                                Spacer(Modifier.height(17.dp))
                                Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                                    Metric(if (teacher) "24" else "82%", if (teacher) "students" else "year average", Green, Modifier.weight(1f))
                                    Metric(if (teacher) "6" else "4", if (teacher) "to review" else "tests completed", Yellow, Modifier.weight(1f))
                                    Metric(if (teacher) "3" else "+8%", if (teacher) "active plans" else "vs last term", Coral, Modifier.weight(1f))
                                }
                            }
                        }
                    }
                    item { SectionHeading(when (page) { "Plans" -> "Weekly plan"; "Tests" -> "Upcoming tests"; "Progress" -> "Your progress"; else -> if (teacher) "Class pulse" else "Next up" }, if (teacher && page == "Home") "VIEW CLASS" else "THIS WEEK") }
                    when (page) {
                        "Plans" -> {
                            item { if (teacher) ActionButton("＋  Add weekly target") { showPlanDialog = true } }
                            if (plans.isEmpty()) item { EmptyState("No weekly targets yet", "Add a focus area and a measurable goal for your class.") }
                            items(plans) { plan -> PlanRow(plan) }
                        }
                        "Tests" -> {
                            if (teacher) item { ActionButton("＋  Create a test") { showTestDialog = true } }
                            if (tests.isEmpty()) item { EmptyState("No tests scheduled", "Create a test for this class to get started.") }
                            items(tests) { test -> TestRow(test, teacher, submissions.any { it.test == test.title }) { startPdfSelection(test) } }
                            if (teacher) item { Text("EVALUATION CRITERIA", color = Teal, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp) }
                            if (teacher) item { CriteriaPanel() }
                        }
                        "Progress" -> {
                            item { PerformanceChart() }
                            item { FocusPanel() }
                            item { Text("RECENT FEEDBACK", color = Teal, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp) }
                            item { FeedbackRow("Algebra · Linear equations", "Show each step before simplifying.", "BUILD ON THIS") }
                            item { FeedbackRow("Biology · Cell structure", "Strong recall. Practise labelled diagrams.", "KEEP GOING") }
                        }
                        "Home" -> {
                            if (teacher) {
                                item { TeacherPulse() }
                                item { Text("CLASS PLAN", color = Teal, fontSize = 11.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp) }
                                items(plans.take(2)) { PlanRow(it) }
                                item { ActionButton("＋  Add weekly target") { showPlanDialog = true } }
                            } else {
                                item { TestRow(tests.first(), false, submissions.any { it.test == tests.first().title }) { startPdfSelection(tests.first()) } }
                                item { FocusPanel() }
                                item { SectionHeading("Recent submissions", "YOUR WORK") }
                                if (submissions.isEmpty()) item { EmptyState("Nothing submitted yet", "Choose a test and upload a PDF of your answer sheet.") }
                                items(submissions.take(2)) { SubmissionRow(it) }
                            }
                        }
                    }
                }
                NavigationBar(selected = page, teacher = teacher) { page = it }
            }
        }
    }

    if (showTestDialog) CreateTestDialog(
        onDismiss = { showTestDialog = false },
        onCreate = { title, subject, kind, date, questions ->
            try {
                tests.add(0, ClassTest(title, subject, kind, date, questions))
                saveTests(prefs, tests)
                Log.i(LogTag, "Test saved locally")
                showTestDialog = false
            } catch (exception: Exception) {
                Log.e(LogTag, "Could not save test", exception)
                errorTitle = "Couldn't save test"
                errorMessage = "The test could not be saved on this device. Please try again."
            }
        }
    )
    if (showPlanDialog) CreatePlanDialog(
        onDismiss = { showPlanDialog = false },
        onCreate = { title, detail ->
            try {
                plans.add(0, StudyPlan(title, detail, "WEEK 04"))
                savePlans(prefs, plans)
                Log.i(LogTag, "Weekly target saved locally")
                showPlanDialog = false
            } catch (exception: Exception) {
                Log.e(LogTag, "Could not save weekly target", exception)
                errorTitle = "Couldn't save target"
                errorMessage = "The weekly target could not be saved on this device. Please try again."
            }
        }
    )
    errorMessage?.let { message ->
        AlertDialog(
            onDismissRequest = { errorMessage = null },
            title = { Text(errorTitle, color = Ink) },
            text = { Text(message, color = Muted) },
            confirmButton = { TextButton(onClick = { errorMessage = null }) { Text("OK", color = Teal) } }
        )
    }
}

@Composable
private fun RoleChip(label: String, selected: Boolean, onClick: () -> Unit) {
    Surface(onClick = onClick, color = if (selected) Teal else Color.White, shape = RoundedCornerShape(20.dp)) {
        Text(label, color = if (selected) Color.White else Muted, fontWeight = FontWeight.SemiBold, fontSize = 12.sp, modifier = Modifier.padding(horizontal = 15.dp, vertical = 9.dp))
    }
}

@Composable
private fun Metric(value: String, label: String, accent: Color, modifier: Modifier = Modifier) {
    Column(modifier.background(Color(0xFF263C39), RoundedCornerShape(6.dp)).padding(10.dp)) {
        Text(value, color = accent, fontSize = 21.sp, fontWeight = FontWeight.Bold)
        Text(label, color = Color(0xFFD1DBD5), fontSize = 10.sp)
    }
}

@Composable
private fun SectionHeading(title: String, eyebrow: String) {
    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Bottom) {
        Text(title, color = Ink, fontSize = 21.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
        Text(eyebrow, color = Muted, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp, modifier = Modifier.padding(bottom = 4.dp))
    }
}

@Composable
private fun TestRow(test: ClassTest, teacher: Boolean, submitted: Boolean, onUpload: () -> Unit) {
    Card(colors = CardDefaults.cardColors(containerColor = Color.White), shape = RoundedCornerShape(7.dp), modifier = Modifier.fillMaxWidth()) {
        Column(Modifier.padding(15.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.SpaceBetween, modifier = Modifier.fillMaxWidth()) {
                Text(test.kind.uppercase(), color = Teal, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
                Text(test.date, color = Muted, fontSize = 11.sp)
            }
            Spacer(Modifier.height(5.dp))
            Text(test.title, color = Ink, fontSize = 18.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold)
            Text("${test.subject}  ·  ${test.questions} questions", color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 3.dp, bottom = 11.dp))
            if (!teacher) OutlinedButton(onClick = onUpload, enabled = !submitted, modifier = Modifier.fillMaxWidth(), shape = RoundedCornerShape(5.dp)) {
                Text(if (submitted) "✓  Answer sheet submitted" else "↑  Upload answer sheet PDF", color = Teal)
            } else Text("Rubric ready  ·  24 students", color = Muted, fontSize = 11.sp)
        }
    }
}

@Composable
private fun PlanRow(plan: StudyPlan) {
    Row(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(14.dp), verticalAlignment = Alignment.CenterVertically) {
        Box(Modifier.size(36.dp).background(Green, RoundedCornerShape(6.dp)), contentAlignment = Alignment.Center) { Text("↗", color = Teal, fontWeight = FontWeight.Bold) }
        Column(Modifier.weight(1f).padding(horizontal = 12.dp)) {
            Text(plan.title, color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
            Text(plan.detail, color = Muted, fontSize = 11.sp, lineHeight = 15.sp)
        }
        Text(plan.week, color = Teal, fontSize = 9.sp, fontWeight = FontWeight.Bold)
    }
}

@Composable
private fun FocusPanel() {
    Column(Modifier.fillMaxWidth().background(Color(0xFFE5F0E5), RoundedCornerShape(7.dp)).padding(16.dp)) {
        Text("YOUR NEXT GOOD STEP", color = Teal, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp)
        Text("Make your working visible.", color = Ink, fontSize = 18.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold, modifier = Modifier.padding(top = 5.dp))
        Text("Your answers are often right. Adding the steps helps you catch small slips and earn method marks.", color = Ink, fontSize = 12.sp, lineHeight = 17.sp, modifier = Modifier.padding(top = 5.dp))
    }
}

@Composable
private fun PerformanceChart() {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(16.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween, verticalAlignment = Alignment.Top) {
            Column { Text("YEARLY PERFORMANCE", color = Teal, fontSize = 9.sp, fontWeight = FontWeight.Bold, letterSpacing = 1.sp); Text("82%", color = Ink, fontSize = 32.sp, fontFamily = FontFamily.Serif, fontWeight = FontWeight.SemiBold) }
            Text("+8% this term", color = Teal, fontSize = 11.sp, fontWeight = FontWeight.SemiBold)
        }
        Spacer(Modifier.height(12.dp))
        val values = listOf(.48f, .62f, .58f, .73f, .68f, .82f, .79f, .9f)
        Canvas(Modifier.fillMaxWidth().height(100.dp)) {
            val gap = 10.dp.toPx()
            val barWidth = (size.width - gap * (values.size - 1)) / values.size
            values.forEachIndexed { index, value ->
                val barHeight = size.height * value
                drawLine(Line, androidx.compose.ui.geometry.Offset(index * (barWidth + gap) + barWidth / 2, 0f), androidx.compose.ui.geometry.Offset(index * (barWidth + gap) + barWidth / 2, size.height), 1.dp.toPx())
                drawLine(if (index == values.lastIndex) Coral else Green, androidx.compose.ui.geometry.Offset(index * (barWidth + gap) + barWidth / 2, size.height), androidx.compose.ui.geometry.Offset(index * (barWidth + gap) + barWidth / 2, size.height - barHeight), barWidth, StrokeCap.Round)
            }
        }
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { listOf("AUG", "OCT", "DEC", "FEB", "APR", "JUN").forEach { Text(it, color = Muted, fontSize = 9.sp) } }
    }
}

@Composable
private fun FeedbackRow(title: String, detail: String, label: String) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(6.dp)).padding(13.dp)) {
        Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) { Text(title, color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 13.sp); Text(label, color = Teal, fontSize = 8.sp, fontWeight = FontWeight.Bold) }
        Text(detail, color = Muted, fontSize = 11.sp, modifier = Modifier.padding(top = 5.dp))
    }
}

@Composable
private fun TeacherPulse() {
    Row(Modifier.fillMaxWidth().background(Color(0xFFFFE7DC), RoundedCornerShape(7.dp)).padding(15.dp), verticalAlignment = Alignment.CenterVertically) {
        Text("↗", color = Ink, fontSize = 24.sp, modifier = Modifier.padding(end = 12.dp))
        Column { Text("2 students need a check-in", color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 14.sp); Text("Fractions and written reasoning are trending down.", color = Muted, fontSize = 11.sp, modifier = Modifier.padding(top = 3.dp)) }
    }
}

@Composable
private fun CriteriaPanel() {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(15.dp)) {
        Text("Algebra test rubric", color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 14.sp)
        Spacer(Modifier.height(10.dp))
        listOf("Method and working" to "40%", "Accuracy" to "35%", "Reasoning" to "25%").forEach { (name, score) ->
            Row(Modifier.fillMaxWidth().padding(vertical = 5.dp), horizontalArrangement = Arrangement.SpaceBetween) { Text(name, color = Muted, fontSize = 12.sp); Text(score, color = Teal, fontSize = 12.sp, fontWeight = FontWeight.Bold) }
        }
    }
}

@Composable
private fun SubmissionRow(submission: Submission) {
    Row(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(6.dp)).padding(13.dp), verticalAlignment = Alignment.CenterVertically) {
        Text("PDF", color = Teal, fontSize = 10.sp, fontWeight = FontWeight.Bold, modifier = Modifier.background(Green, RoundedCornerShape(4.dp)).padding(horizontal = 7.dp, vertical = 6.dp))
        Column(Modifier.weight(1f).padding(horizontal = 10.dp)) { Text(submission.test, color = Ink, fontWeight = FontWeight.SemiBold, fontSize = 12.sp); Text(submission.file, color = Muted, fontSize = 10.sp) }
        Text(submission.status, color = Teal, fontSize = 9.sp)
    }
}

@Composable
private fun EmptyState(title: String, detail: String) {
    Column(Modifier.fillMaxWidth().background(Color.White, RoundedCornerShape(7.dp)).padding(18.dp)) {
        Text(title, color = Ink, fontWeight = FontWeight.SemiBold)
        Text(detail, color = Muted, fontSize = 12.sp, modifier = Modifier.padding(top = 4.dp))
    }
}

@Composable
private fun ActionButton(label: String, onClick: () -> Unit) {
    Button(onClick = onClick, modifier = Modifier.fillMaxWidth(), colors = ButtonDefaults.buttonColors(containerColor = Teal), shape = RoundedCornerShape(5.dp)) { Text(label, color = Color.White) }
}

@Composable
private fun NavigationBar(selected: String, teacher: Boolean, onSelect: (String) -> Unit) {
    val pages = listOf("Home", "Plans", "Tests", "Progress")
    Row(Modifier.fillMaxWidth().background(Color.White).padding(horizontal = 12.dp, vertical = 9.dp), horizontalArrangement = Arrangement.SpaceAround) {
        pages.forEach { item ->
            Column(Modifier.clickable { onSelect(item) }.padding(horizontal = 8.dp, vertical = 3.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                Text(when (item) { "Home" -> "⌂"; "Plans" -> "▤"; "Tests" -> "▣"; else -> "⌁" }, color = if (selected == item) Teal else Muted, fontSize = 19.sp)
                Text(item, color = if (selected == item) Teal else Muted, fontSize = 9.sp, fontWeight = if (selected == item) FontWeight.Bold else FontWeight.Normal)
            }
        }
    }
}

@Composable
private fun CreateTestDialog(onDismiss: () -> Unit, onCreate: (String, String, String, String, Int) -> Unit) {
    var title by remember { mutableStateOf("") }
    var subject by remember { mutableStateOf("Mathematics") }
    var kind by remember { mutableStateOf("Lecture test") }
    var date by remember { mutableStateOf("Fri, 17 Oct") }
    var questions by remember { mutableStateOf("10") }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Create a test", color = Ink, fontFamily = FontFamily.Serif) }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(title, { title = it }, label = { Text("Test name") }, singleLine = true)
            OutlinedTextField(subject, { subject = it }, label = { Text("Subject") }, singleLine = true)
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                listOf("Lecture test", "Cumulative").forEach { choice ->
                    TextButton(onClick = { kind = choice }) { Text(if (kind == choice) "● $choice" else choice, color = Teal, fontSize = 11.sp) }
                }
            }
            OutlinedTextField(date, { date = it }, label = { Text("Due date") }, singleLine = true)
            OutlinedTextField(questions, { questions = it.filter(Char::isDigit) }, label = { Text("Number of questions") }, singleLine = true)
        }
    }, confirmButton = { TextButton(onClick = { if (title.isNotBlank()) onCreate(title, subject, kind, date, questions.toIntOrNull() ?: 0) }) { Text("Create", color = Teal) } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = Muted) } })
}

@Composable
private fun CreatePlanDialog(onDismiss: () -> Unit, onCreate: (String, String) -> Unit) {
    var title by remember { mutableStateOf("") }
    var detail by remember { mutableStateOf("") }
    AlertDialog(onDismissRequest = onDismiss, title = { Text("Weekly target", color = Ink, fontFamily = FontFamily.Serif) }, text = {
        Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(title, { title = it }, label = { Text("Focus area") }, singleLine = true)
            OutlinedTextField(detail, { detail = it }, label = { Text("Measurable goal") }, minLines = 2)
        }
    }, confirmButton = { TextButton(onClick = { if (title.isNotBlank()) onCreate(title, detail) }) { Text("Add target", color = Teal) } }, dismissButton = { TextButton(onClick = onDismiss) { Text("Cancel", color = Muted) } })
}

private fun loadTests(prefs: android.content.SharedPreferences): List<ClassTest> {
    val defaults = listOf(ClassTest("Linear equations", "Mathematics", "Lecture test", "Tomorrow · 10:30", 12), ClassTest("Cells & tissues", "Biology", "Cumulative", "Thu, 16 Oct", 20))
    val raw = prefs.getString("tests", null) ?: return defaults
    return runCatching { JSONArray(raw).let { array -> (0 until array.length()).map { array.getJSONObject(it).let { obj -> ClassTest(obj.getString("title"), obj.getString("subject"), obj.getString("kind"), obj.getString("date"), obj.getInt("questions")) } } } }.getOrDefault(defaults)
}

private fun saveTests(prefs: android.content.SharedPreferences, tests: List<ClassTest>) {
    prefs.edit().putString("tests", JSONArray().apply { tests.forEach { put(JSONObject().put("title", it.title).put("subject", it.subject).put("kind", it.kind).put("date", it.date).put("questions", it.questions)) } }.toString()).apply()
}

private fun loadPlans(prefs: android.content.SharedPreferences): List<StudyPlan> {
    val defaults = listOf(StudyPlan("Linear equations", "Practise balancing and checking solutions", "WEEK 04"), StudyPlan("Written reasoning", "Explain one answer using a complete sentence", "WEEK 04"))
    val raw = prefs.getString("plans", null) ?: return defaults
    return runCatching { JSONArray(raw).let { array -> (0 until array.length()).map { array.getJSONObject(it).let { obj -> StudyPlan(obj.getString("title"), obj.getString("detail"), obj.getString("week")) } } } }.getOrDefault(defaults)
}

private fun savePlans(prefs: android.content.SharedPreferences, plans: List<StudyPlan>) {
    prefs.edit().putString("plans", JSONArray().apply { plans.forEach { put(JSONObject().put("title", it.title).put("detail", it.detail).put("week", it.week)) } }.toString()).apply()
}

private fun loadSubmissions(prefs: android.content.SharedPreferences): List<Submission> {
    val raw = prefs.getString("submissions", null) ?: return emptyList()
    return runCatching { JSONArray(raw).let { array -> (0 until array.length()).map { array.getJSONObject(it).let { obj -> Submission(obj.getString("test"), obj.getString("file"), obj.getString("status")) } } } }.getOrDefault(emptyList())
}

private fun saveSubmissions(prefs: android.content.SharedPreferences, submissions: List<Submission>) {
    prefs.edit().putString("submissions", JSONArray().apply { submissions.forEach { put(JSONObject().put("test", it.test).put("file", it.file).put("status", it.status)) } }.toString()).apply()
}