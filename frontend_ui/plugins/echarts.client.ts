import { defineNuxtPlugin } from '#app'
import { use } from 'echarts/core'
import { CanvasRenderer } from 'echarts/renderers'
import {
  BarChart,
  LineChart,
  PieChart,
  TreemapChart,
  HeatmapChart,
  ScatterChart,
  RadarChart,
  GaugeChart,
  FunnelChart,
  CandlestickChart,
} from 'echarts/charts'
import {
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  ToolboxComponent,
  VisualMapComponent,
  RadarComponent,
} from 'echarts/components'
import VChart from 'vue-echarts'

use([
  CanvasRenderer,
  BarChart,
  LineChart,
  PieChart,
  TreemapChart,
  HeatmapChart,
  ScatterChart,
  RadarChart,
  GaugeChart,
  FunnelChart,
  CandlestickChart,
  GridComponent,
  TooltipComponent,
  LegendComponent,
  TitleComponent,
  DataZoomComponent,
  ToolboxComponent,
  VisualMapComponent,
  RadarComponent,
])

export default defineNuxtPlugin((nuxtApp) => {
  nuxtApp.vueApp.component('VChart', VChart)
})
