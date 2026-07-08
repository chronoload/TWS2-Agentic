<template>
  <div class="lesson-timeline">
    <div v-for="group in groupedLessons" :key="group.sectionNumber" class="lesson-timeline__group">
      <div class="lesson-timeline__section-title">
        §{{ group.sectionNumber }} {{ group.sectionTitle }}
      </div>
      <div v-for="lesson in group.lessons" :key="lesson.lesson_number" class="lesson-timeline__item">
        <div class="lesson-timeline__dot" :class="getStatusClass(lesson)"></div>
        <div class="lesson-timeline__content">
          <div class="lesson-timeline__top">
            <span class="lesson-timeline__number">第{{ lesson.lesson_number }}课</span>
            <span class="lesson-timeline__hours">{{ getSafeEstimatedHours(lesson) }} 学时</span>
          </div>
          <div class="lesson-timeline__title">{{ lesson.lesson_title }}</div>
          <div v-if="lesson.central_question" class="lesson-timeline__question">
            {{ lesson.central_question }}
          </div>
          <label class="lesson-timeline__check" @click.stop>
            <input
              type="checkbox"
              :checked="isCompleted(lesson)"
              @change="toggleLesson(lesson)"
            />
            <span>{{ isCompleted(lesson) ? '已完成' : '标记完成' }}</span>
          </label>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { updateLessonStatus } from '../api'

interface LessonItem {
  lesson_number: number
  lesson_title: string
  section: number
  description: string
  central_question: string
  references: string[]
  estimated_hours: number
}

interface SectionItem {
  section_number: number
  section_title: string
  section_hours: number
  lesson_range: string
}

const props = defineProps<{
  lessons: LessonItem[]
  sections: SectionItem[]
  courseId: string
  progress: Record<string, { status: string; updated_at: string }>
}>()

const emit = defineEmits<{ statusChanged: [] }>()

// 安全获取课时学时
function getSafeEstimatedHours(lesson: LessonItem): number {
  let val = lesson.estimated_hours
  if (val === null || val === undefined || val === '') {
    return 1
  }
  const num = Number(val)
  return Number.isFinite(num) && num >= 0 ? num : 1
}

const groupedLessons = computed(() => {
  const sectionMap = new Map<number, string>()
  for (const s of props.sections) {
    sectionMap.set(s.section_number, s.section_title)
  }
  const groups: Array<{ sectionNumber: number; sectionTitle: string; lessons: LessonItem[] }> = []
  const seen = new Set<number>()
  for (const lesson of props.lessons) {
    // 确保课时有安全的学时值
    if (!('estimated_hours' in lesson) || lesson.estimated_hours === undefined || lesson.estimated_hours === null) {
      ;(lesson as any).estimated_hours = 1
    }
    if (!seen.has(lesson.section)) {
      seen.add(lesson.section)
      groups.push({
        sectionNumber: lesson.section,
        sectionTitle: sectionMap.get(lesson.section) ?? `第${lesson.section}节`,
        lessons: [],
      })
    }
    groups[groups.length - 1].lessons.push(lesson)
  }
  return groups
})

function isCompleted(lesson: LessonItem) {
  return props.progress?.[String(lesson.lesson_number)]?.status === 'completed'
}

function getStatusClass(lesson: LessonItem) {
  const status = props.progress?.[String(lesson.lesson_number)]?.status
  if (status === 'completed') return 'dot--completed'
  if (status === 'in_progress') return 'dot--in-progress'
  return 'dot--not-started'
}

async function toggleLesson(lesson: LessonItem) {
  const newStatus = isCompleted(lesson) ? 'not_started' : 'completed'
  await updateLessonStatus(props.courseId, lesson.lesson_number, newStatus)
  emit('statusChanged')
}
</script>

<style scoped>
.lesson-timeline {
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.lesson-timeline__section-title {
  font-size: 14px;
  font-weight: 600;
  color: var(--accent);
  padding-bottom: 6px;
  border-bottom: 1px solid var(--border);
}

.lesson-timeline__item {
  display: flex;
  gap: 12px;
  padding: 10px 0;
  position: relative;
}

.lesson-timeline__dot {
  width: 12px;
  height: 12px;
  border-radius: 50%;
  margin-top: 4px;
  flex-shrink: 0;
  border: 2px solid var(--border);
  background: var(--bg);
}

.lesson-timeline__dot.dot--completed {
  background: var(--success);
  border-color: var(--success);
}

.lesson-timeline__dot.dot--in-progress {
  background: var(--warning);
  border-color: var(--warning);
}

.lesson-timeline__dot.dot--not-started {
  background: var(--bg);
  border-color: var(--border);
}

.lesson-timeline__content {
  flex: 1;
  min-width: 0;
}

.lesson-timeline__top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}

.lesson-timeline__number {
  font-size: 12px;
  color: var(--fg-muted);
}

.lesson-timeline__hours {
  font-size: 11px;
  color: var(--fg-muted);
  background: var(--bg);
  padding: 1px 6px;
  border-radius: 8px;
}

.lesson-timeline__title {
  font-size: 14px;
  font-weight: 500;
  color: var(--fg);
  margin-bottom: 4px;
}

.lesson-timeline__question {
  font-size: 12px;
  color: var(--fg-muted);
  line-height: 1.5;
  margin-bottom: 6px;
}

.lesson-timeline__check {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  font-size: 12px;
  color: var(--fg-muted);
  user-select: none;
}

.lesson-timeline__check input {
  width: 16px;
  height: 16px;
  accent-color: var(--success);
  cursor: pointer;
}
</style>
