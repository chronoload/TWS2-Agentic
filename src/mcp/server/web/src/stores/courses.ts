import { defineStore } from 'pinia'
import { ref } from 'vue'
import { getCourses, getCourseProgress, updateLessonStatus } from '../api'

export interface Lesson {
  lesson_number: number
  lesson_title: string
  section?: number
  description?: string
  central_question?: string
  references?: string[]
  estimated_hours?: number
}

export interface Course {
  note_id: string
  course_title: string
  total_hours?: number
  sections?: Array<{
    section_number: number
    section_title: string
    section_hours?: number
  }>
  lessons?: Lesson[]
  filename?: string
}

export const useCoursesStore = defineStore('courses', () => {
  const courses = ref<Course[]>([])
  const loading = ref(false)

  async function fetchCourses() {
    loading.value = true
    try {
      const res = await getCourses()
      const apiData = res.data?.data ?? res.data
      courses.value = apiData?.courses ?? (Array.isArray(apiData) ? apiData : [])
    } finally {
      loading.value = false
    }
  }

  async function fetchProgress(courseId: string) {
    const res = await getCourseProgress(courseId)
    const apiData = res.data?.data ?? res.data
    return apiData?.lessons ?? {}
  }

  async function setLessonStatus(courseId: string, lessonNumber: number, status: string) {
    await updateLessonStatus(courseId, lessonNumber, status)
  }

  return { courses, loading, fetchCourses, fetchProgress, setLessonStatus }
})
