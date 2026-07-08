<template>
  <div class="course-card" :class="{ active: active }" @click="$emit('select', course)">
    <div class="course-card__header">
      <h3 class="course-card__title">{{ course.course_title }}</h3>
      <span class="course-card__hours">{{ course.total_hours }} 学时</span>
    </div>
    <div class="course-card__progress">
      <div class="course-card__progress-bar">
        <div class="course-card__progress-fill" :style="{ width: progressPercent + '%' }"></div>
      </div>
      <span class="course-card__progress-text">{{ completedCount }}/{{ totalLessons }} 课时</span>
    </div>
    <div class="course-card__sections">
      <span v-for="section in course.sections" :key="section.section_number" class="course-card__section-tag">
        §{{ section.section_number }} {{ section.section_title }}
      </span>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  course: {
    filename: string
    note_id: string
    course_title: string
    total_hours: number
    sections: Array<{ section_number: number; section_title: string; section_hours: number; lesson_range: string }>
    lessons: Array<{ lesson_number: number; lesson_title: string; section: number; description: string; central_question: string; references: string[]; estimated_hours: number }>
  }
  progress: Record<string, { status: string; updated_at: string }>
  active?: boolean
}>()

defineEmits<{ select: [course: typeof props.course] }>()

const totalLessons = computed(() => props.course.lessons?.length ?? 0)

const completedCount = computed(() => {
  if (!props.progress) return 0
  return props.course.lessons?.filter(l => props.progress[String(l.lesson_number)]?.status === 'completed').length ?? 0
})

const progressPercent = computed(() => {
  if (totalLessons.value === 0) return 0
  return Math.round((completedCount.value / totalLessons.value) * 100)
})
</script>

<style scoped>
.course-card {
  background: var(--card);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s;
}

.course-card:hover {
  border-color: var(--accent);
}

.course-card.active {
  border-color: var(--accent);
  box-shadow: 0 0 0 1px var(--accent);
}

.course-card__header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 8px;
  margin-bottom: 10px;
}

.course-card__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--fg);
  line-height: 1.4;
  flex: 1;
}

.course-card__hours {
  font-size: 12px;
  color: var(--fg-muted);
  white-space: nowrap;
  background: var(--bg);
  padding: 2px 8px;
  border-radius: 10px;
}

.course-card__progress {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.course-card__progress-bar {
  flex: 1;
  height: 6px;
  background: var(--bg);
  border-radius: 3px;
  overflow: hidden;
}

.course-card__progress-fill {
  height: 100%;
  background: var(--success);
  border-radius: 3px;
  transition: width 0.3s;
}

.course-card__progress-text {
  font-size: 12px;
  color: var(--fg-muted);
  white-space: nowrap;
}

.course-card__sections {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.course-card__section-tag {
  font-size: 11px;
  color: var(--accent);
  background: rgba(122, 162, 247, 0.1);
  padding: 2px 8px;
  border-radius: 10px;
  white-space: nowrap;
}
</style>
