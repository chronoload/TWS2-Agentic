<template>
  <div class="view">
    <header class="view-header">
      <h1>课程执行</h1>
    </header>
    <div class="view-body exec-body">
      <div class="exec-selectors">
        <div class="exec-field">
          <label class="exec-field__label">选择课程</label>
          <select v-model="selectedCourseId" class="exec-field__select" @change="onCourseChange">
            <option value="">-- 请选择课程 --</option>
            <option v-for="course in courses" :key="course.note_id" :value="course.note_id">
              {{ course.course_title }}
            </option>
          </select>
        </div>
        <div class="exec-field">
          <label class="exec-field__label">选择课时</label>
          <select v-model="selectedLessonNum" class="exec-field__select" @change="onLessonChange">
            <option value="">-- 请选择课时 --</option>
            <option v-for="lesson in currentLessons" :key="lesson.lesson_number" :value="lesson.lesson_number">
              第{{ lesson.lesson_number }}课 - {{ lesson.lesson_title }}
            </option>
          </select>
        </div>
      </div>

      <div v-if="currentLesson" class="exec-lesson">
        <div class="exec-lesson__header">
          <h2 class="exec-lesson__title">{{ currentLesson.lesson_title }}</h2>
          <span class="exec-lesson__hours">{{ getSafeEstimatedHours(currentLesson) }} 学时</span>
        </div>

        <div v-if="currentLesson.central_question" class="exec-lesson__question">
          <span class="exec-lesson__question-label">核心问题</span>
          {{ currentLesson.central_question }}
        </div>

        <div v-if="currentLesson.description" class="exec-lesson__desc">
          {{ currentLesson.description }}
        </div>

        <div v-if="currentLesson.references?.length" class="exec-lesson__refs">
          <span class="exec-lesson__refs-label">参考资料</span>
          <ul>
            <li v-for="(ref, i) in currentLesson.references" :key="i">{{ ref }}</li>
          </ul>
        </div>

        <ExecTimer :duration="(currentLesson.estimated_hours || 0) * 60" />

        <button class="exec-lesson__complete" @click="completeLesson">
          完成课时
        </button>
      </div>

      <div v-else class="exec-lesson__empty">
        请选择课程和课时开始学习
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { getCourses, getCourseProgress, updateLessonStatus } from '../api'
import ExecTimer from '../components/ExecTimer.vue'

interface LessonData {
  lesson_number: number
  lesson_title: string
  section: number
  description: string
  central_question: string
  references: string[]
  estimated_hours: number
}

interface CourseData {
  filename: string
  note_id: string
  course_title: string
  total_hours: number
  sections: Array<{ section_number: number; section_title: string; section_hours: number; lesson_range: string }>
  lessons: LessonData[]
}

// 安全获取课时学时
function getSafeEstimatedHours(lesson: LessonData): number {
  let val = lesson.estimated_hours
  if (val === null || val === undefined || val === '') {
    return 1
  }
  const num = Number(val)
  return Number.isFinite(num) && num >= 0 ? num : 1
}

const courses = ref<CourseData[]>([])
const selectedCourseId = ref('')
const selectedLessonNum = ref<number | string>('')
const progress = ref<Record<string, { status: string; updated_at: string }>>({})
const route = useRoute()

const currentCourse = computed(() => courses.value.find(c => c.note_id === selectedCourseId.value) ?? null)
const currentLessons = computed(() => currentCourse.value?.lessons ?? [])
const currentLesson = computed(() => {
  if (!selectedLessonNum.value) return null
  return currentLessons.value.find(l => l.lesson_number === Number(selectedLessonNum.value)) ?? null
})

onMounted(async () => {
  try {
    const res = await getCourses()
    const apiData = res.data?.data ?? res.data
    courses.value = apiData?.courses ?? (Array.isArray(apiData) ? apiData : [])
  } catch {
    courses.value = []
  }
  // 如果有 query 参数 course，自动选中对应课程
  const courseName = route.query.course as string | undefined
  if (courseName && courses.value.length > 0) {
    const match = courses.value.find(c => c.course_title === courseName || c.note_id === courseName)
    if (match) {
      selectedCourseId.value = match.note_id
      await onCourseChange()
    }
  }
})

async function onCourseChange() {
  selectedLessonNum.value = ''
  if (!selectedCourseId.value) return
  try {
    const res = await getCourseProgress(selectedCourseId.value)
    const apiData = res.data?.data ?? res.data
    progress.value = apiData?.lessons ?? {}
  } catch {
    progress.value = {}
  }
  autoSelectNextLesson()
}

function onLessonChange() {
  // lesson changed
}

function autoSelectNextLesson() {
  if (!currentCourse.value) return
  const lessons = currentCourse.value.lessons
  const next = lessons.find(l => progress.value[String(l.lesson_number)]?.status !== 'completed')
  if (next) {
    selectedLessonNum.value = next.lesson_number
  } else if (lessons.length > 0) {
    selectedLessonNum.value = lessons[0].lesson_number
  }
}

async function completeLesson() {
  if (!selectedCourseId.value || !selectedLessonNum.value) return
  await updateLessonStatus(selectedCourseId.value, Number(selectedLessonNum.value), 'completed')
  // refresh progress
  try {
    const res = await getCourseProgress(selectedCourseId.value)
    progress.value = res.data?.lessons ?? res.data ?? {}
  } catch {
    progress.value = {}
  }
  // auto advance to next lesson
  if (currentCourse.value) {
    const lessons = currentCourse.value.lessons
    const currentIdx = lessons.findIndex(l => l.lesson_number === Number(selectedLessonNum.value))
    // find next uncompleted after current
    let next = lessons.slice(currentIdx + 1).find(l => progress.value[String(l.lesson_number)]?.status !== 'completed')
    if (!next) {
      next = lessons.slice(0, currentIdx).find(l => progress.value[String(l.lesson_number)]?.status !== 'completed')
    }
    if (next) {
      selectedLessonNum.value = next.lesson_number
    }
  }
}
</script>

<style scoped>
.exec-body {
  max-width: 600px;
  margin: 0 auto;
}

.exec-selectors {
  display: flex;
  flex-direction: column;
  gap: 12px;
  margin-bottom: 20px;
}

.exec-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.exec-field__label {
  font-size: 13px;
  color: var(--fg-muted);
  font-weight: 500;
}

.exec-field__select {
  width: 100%;
  padding: 10px 12px;
  font-size: 14px;
}

.exec-lesson {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 20px;
}

.exec-lesson__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  margin-bottom: 16px;
}

.exec-lesson__title {
  font-size: 18px;
  font-weight: 600;
  color: var(--fg);
}

.exec-lesson__hours {
  font-size: 12px;
  color: var(--fg-muted);
  background: var(--bg);
  padding: 3px 10px;
  border-radius: 10px;
  white-space: nowrap;
}

.exec-lesson__question {
  background: rgba(122, 162, 247, 0.08);
  border-left: 3px solid var(--accent);
  padding: 10px 14px;
  border-radius: 0 8px 8px 0;
  margin-bottom: 14px;
  font-size: 14px;
  line-height: 1.6;
  color: var(--fg);
}

.exec-lesson__question-label {
  display: block;
  font-size: 11px;
  color: var(--accent);
  font-weight: 600;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 1px;
}

.exec-lesson__desc {
  font-size: 14px;
  line-height: 1.7;
  color: var(--fg-muted);
  margin-bottom: 14px;
}

.exec-lesson__refs {
  margin-bottom: 16px;
}

.exec-lesson__refs-label {
  display: block;
  font-size: 12px;
  color: var(--fg-muted);
  font-weight: 600;
  margin-bottom: 6px;
}

.exec-lesson__refs ul {
  list-style: none;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.exec-lesson__refs li {
  font-size: 13px;
  color: var(--fg-muted);
  padding-left: 14px;
  position: relative;
}

.exec-lesson__refs li::before {
  content: '•';
  position: absolute;
  left: 0;
  color: var(--accent);
}

.exec-lesson__complete {
  width: 100%;
  padding: 12px;
  font-size: 15px;
  font-weight: 600;
  background: var(--success);
  color: var(--bg);
  border-radius: 8px;
  margin-top: 8px;
}

.exec-lesson__complete:hover {
  background: #b5e88c;
}

.exec-lesson__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 200px;
  color: var(--fg-muted);
  font-size: 14px;
}
</style>
