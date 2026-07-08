<template>
  <div class="view">
    <header class="view-header">
      <h1>课程表</h1>
    </header>
    <div class="courses-layout">
      <div class="courses-layout__list">
        <div v-if="loading" class="courses-layout__empty">加载中...</div>
        <div v-else-if="courses.length === 0" class="courses-layout__empty">暂无课程</div>
        <CourseCard
          v-for="course in courses"
          :key="course.note_id"
          :course="course"
          :progress="progressMap[course.note_id] ?? {}"
          :active="selectedCourseId === course.note_id"
          @select="selectCourse"
        />
      </div>
      <div class="courses-layout__detail">
        <div v-if="!selectedCourse" class="courses-layout__empty">请选择一门课程</div>
        <template v-else>
          <div class="courses-layout__detail-header">
            <h2>{{ selectedCourse.course_title }}</h2>
            <span class="courses-layout__detail-hours">{{ selectedCourse.total_hours }} 学时</span>
          </div>
          <LessonTimeline
            :lessons="selectedCourse.lessons"
            :sections="selectedCourse.sections"
            :course-id="selectedCourse.note_id"
            :progress="progressMap[selectedCourse.note_id] ?? {}"
            @status-changed="refreshProgress"
          />
        </template>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { getCourses, getCourseProgress } from '../api'
import CourseCard from '../components/CourseCard.vue'
import LessonTimeline from '../components/LessonTimeline.vue'

interface CourseData {
  filename: string
  note_id: string
  course_title: string
  total_hours: number
  sections: Array<{ section_number: number; section_title: string; section_hours: number; lesson_range: string }>
  lessons: Array<{ lesson_number: number; lesson_title: string; section: number; description: string; central_question: string; references: string[]; estimated_hours: number }>
}

const courses = ref<CourseData[]>([])
const loading = ref(false)
const selectedCourseId = ref<string | null>(null)
const progressMap = ref<Record<string, Record<string, { status: string; updated_at: string }>>>({})

const selectedCourse = ref<CourseData | null>(null)

onMounted(async () => {
  // 优先从 bootstrap 缓存加载
  const bootstrap = (window as any).__TS2_BOOTSTRAP__
  if (bootstrap?.courses) {
    const apiData = bootstrap.courses
    courses.value = apiData?.courses ?? (Array.isArray(apiData) ? apiData : [])
    delete bootstrap.courses
  }
  // 后台刷新
  loading.value = true
  try {
    const res = await getCourses()
    const apiData = res.data?.data ?? res.data
    courses.value = apiData?.courses ?? (Array.isArray(apiData) ? apiData : [])
  } finally {
    loading.value = false
  }
})

async function selectCourse(course: CourseData) {
  selectedCourseId.value = course.note_id
  selectedCourse.value = course
  await loadProgress(course.note_id)
}

async function loadProgress(courseId: string) {
  try {
    const res = await getCourseProgress(courseId)
    const apiData = res.data?.data ?? res.data
    progressMap.value[courseId] = apiData?.lessons ?? {}
  } catch {
    progressMap.value[courseId] = {}
  }
}

async function refreshProgress() {
  if (selectedCourseId.value) {
    await loadProgress(selectedCourseId.value)
  }
}
</script>

<style scoped>
.courses-layout {
  display: flex;
  flex: 1;
  min-height: 0;
  padding: 12px;
  gap: 12px;
}

.courses-layout__list {
  width: 320px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  padding-right: 4px;
}

.courses-layout__detail {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 16px;
  background: var(--card);
  border-radius: 10px;
  border: 1px solid var(--border);
}

.courses-layout__detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
}

.courses-layout__detail-header h2 {
  font-size: 18px;
  font-weight: 600;
  color: var(--fg);
}

.courses-layout__detail-hours {
  font-size: 13px;
  color: var(--fg-muted);
  background: var(--bg);
  padding: 4px 10px;
  border-radius: 10px;
}

.courses-layout__empty {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  min-height: 120px;
  color: var(--fg-muted);
  font-size: 14px;
}

@media (max-width: 768px) {
  .courses-layout {
    flex-direction: column;
  }

  .courses-layout__list {
    width: 100%;
    max-height: 240px;
    flex-shrink: 0;
  }

  .courses-layout__detail {
    flex: 1;
  }
}
</style>
