'use client'

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { 
  Brain, 
  TrendingUp, 
  AlertTriangle, 
  BarChart3, 
  PieChart, 
  Activity,
  Target,
  Shield,
  Zap
} from 'lucide-react'
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  PieChart as RePieChart,
  Pie,
  Cell,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts'

interface AnomalyData {
  id: string
  type: string
  severity: 'high' | 'medium' | 'low'
  description: string
  timestamp: string
  score: number
}

interface RiskPrediction {
  date: string
  riskLevel: 'low' | 'medium' | 'high' | 'critical'
  confidence: number
  riskFactors: string[]
}

interface SentimentData {
  overallSentiment: 'positive' | 'negative' | 'neutral'
  confidence: number
  individualAnalyses: Array<{
    text: string
    sentiment: string
    confidence: number
    keywords: string[]
  }>
}

interface PatternData {
  patternType: string
  description: string
  data: Record<string, number>
}

const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884D8']

export default function AnalyticsPage() {
  const [anomalies, setAnomalies] = useState<AnomalyData[]>([])
  const [riskPredictions, setRiskPredictions] = useState<RiskPrediction[]>([])
  const [sentimentData, setSentimentData] = useState<SentimentData | null>(null)
  const [patterns, setPatterns] = useState<PatternData[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedTab, setSelectedTab] = useState('overview')

  useEffect(() => {
    fetchAnalyticsData()
  }, [])

  const fetchAnalyticsData = async () => {
    try {
      setLoading(true)
      
      // Mock data - in production, fetch from API
      const mockAnomalies: AnomalyData[] = [
        {
          id: '1',
          type: 'duration_anomaly',
          severity: 'high',
          description: 'Unusually long audit duration detected',
          timestamp: '2026-03-10T10:30:00Z',
          score: 0.85
        },
        {
          id: '2',
          type: 'findings_anomaly',
          severity: 'medium',
          description: 'High number of findings in recent audit',
          timestamp: '2026-03-10T09:15:00Z',
          score: 0.65
        }
      ]

      const mockRiskPredictions: RiskPrediction[] = Array.from({ length: 30 }, (_, i) => ({
        date: new Date(Date.now() + i * 24 * 60 * 60 * 1000).toISOString().split('T')[0],
        riskLevel: ['low', 'medium', 'high', 'critical'][Math.floor(Math.random() * 4)] as any,
        confidence: Math.random() * 0.3 + 0.7,
        riskFactors: ['Elevated complexity', 'Resource constraints', 'Timeline pressure']
      }))

      const mockSentimentData: SentimentData = {
        overallSentiment: 'positive',
        confidence: 0.78,
        individualAnalyses: [
          {
            text: 'Audit completed successfully with excellent results',
            sentiment: 'positive',
            confidence: 0.92,
            keywords: ['excellent', 'successful']
          },
          {
            text: 'Minor issues found but overall process smooth',
            sentiment: 'neutral',
            confidence: 0.65,
            keywords: ['minor', 'smooth']
          }
        ]
      }

      const mockPatterns: PatternData[] = [
        {
          patternType: 'peak_audit_hours',
          description: 'Most active audit hours',
          data: { '9:00': 15, '10:00': 25, '11:00': 20, '14:00': 18, '15:00': 22 }
        },
        {
          patternType: 'risk_distribution',
          description: 'Risk score distribution',
          data: { 'Low': 45, 'Medium': 30, 'High': 20, 'Critical': 5 }
        }
      ]

      setAnomalies(mockAnomalies)
      setRiskPredictions(mockRiskPredictions)
      setSentimentData(mockSentimentData)
      setPatterns(mockPatterns)
    } catch (error) {
      console.error('Failed to fetch analytics data:', error)
    } finally {
      setLoading(false)
    }
  }

  const getSeverityColor = (severity: string) => {
    switch (severity) {
      case 'high': return 'bg-red-500'
      case 'medium': return 'bg-yellow-500'
      case 'low': return 'bg-green-500'
      default: return 'bg-gray-500'
    }
  }

  const getRiskColor = (riskLevel: string) => {
    switch (riskLevel) {
      case 'critical': return '#FF4444'
      case 'high': return '#FF8800'
      case 'medium': return '#FFBB33'
      case 'low': return '#00C851'
      default: return '#888888'
    }
  }

  const pieChartData = patterns.find(p => p.patternType === 'risk_distribution')?.data || {}

  const pieData = Object.entries(pieChartData).map(([name, value]) => ({
    name,
    value
  }))

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">ML Analytics Dashboard</h1>
          <p className="text-muted-foreground">
            AI-powered insights and predictive analytics for audit operations
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="sm">
            <Brain className="mr-2 h-4 w-4" />
            Train Models
          </Button>
          <Button size="sm">
            <Activity className="mr-2 h-4 w-4" />
            Refresh Data
          </Button>
        </div>
      </div>

      <Tabs value={selectedTab} onValueChange={setSelectedTab} className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="anomalies">Anomalies</TabsTrigger>
          <TabsTrigger value="predictions">Predictions</TabsTrigger>
          <TabsTrigger value="patterns">Patterns</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Anomalies Detected</CardTitle>
                <AlertTriangle className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{anomalies.length}</div>
                <p className="text-xs text-muted-foreground">
                  {anomalies.filter(a => a.severity === 'high').length} high severity
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Risk Predictions</CardTitle>
                <TrendingUp className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{riskPredictions.length}</div>
                <p className="text-xs text-muted-foreground">
                  Next 30 days forecast
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Sentiment Score</CardTitle>
                <BarChart3 className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">
                  {sentimentData ? `${Math.round(sentimentData.confidence * 100)}%` : '0%'}
                </div>
                <p className="text-xs text-muted-foreground">
                  {sentimentData?.overallSentiment || 'N/A'} sentiment
                </p>
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">ML Accuracy</CardTitle>
                <Target className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">87%</div>
                <p className="text-xs text-muted-foreground">
                  Model confidence
                </p>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Risk Prediction Trend</CardTitle>
                <CardDescription>30-day risk forecast</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={riskPredictions.slice(0, 14)}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="date" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line 
                      type="monotone" 
                      dataKey="confidence" 
                      stroke="#8884d8" 
                      strokeWidth={2}
                      name="Confidence"
                    />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Risk Distribution</CardTitle>
                <CardDescription>Risk level breakdown</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <RePieChart>
                    <Pie
                      data={pieData}
                      cx="50%"
                      cy="50%"
                      labelLine={false}
                      label={({ name, percent }) => `${name} ${((percent || 0) * 100).toFixed(0)}%`}
                      outerRadius={80}
                      fill="#8884d8"
                      dataKey="value"
                    >
                      {pieData.map((entry, index) => (
                        <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </RePieChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="anomalies" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Detected Anomalies</CardTitle>
              <CardDescription>
                Unusual patterns detected by ML algorithms
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {anomalies.map((anomaly) => (
                  <div key={anomaly.id} className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="flex items-center space-x-4">
                      <div className={`w-3 h-3 rounded-full ${getSeverityColor(anomaly.severity)}`} />
                      <div>
                        <p className="font-medium">{anomaly.description}</p>
                        <p className="text-sm text-muted-foreground">
                          {anomaly.timestamp} • Score: {anomaly.score.toFixed(2)}
                        </p>
                      </div>
                    </div>
                    <Badge variant={anomaly.severity === 'high' ? 'destructive' : 'secondary'}>
                      {anomaly.severity}
                    </Badge>
                  </div>
                ))}
                {anomalies.length === 0 && (
                  <div className="text-center py-8 text-muted-foreground">
                    <Shield className="mx-auto h-12 w-12 mb-4 opacity-50" />
                    <p>No anomalies detected</p>
                  </div>
                )}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="predictions" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Risk Predictions</CardTitle>
              <CardDescription>
                30-day risk forecast with confidence levels
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ResponsiveContainer width="100%" height={400}>
                <AreaChart data={riskPredictions}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Legend />
                  <Area 
                    type="monotone" 
                    dataKey="confidence" 
                    stroke="#8884d8" 
                    fill="#8884d8"
                    fillOpacity={0.6}
                    name="Risk Confidence"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="patterns" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            {patterns.map((pattern, index) => (
              <Card key={index}>
                <CardHeader>
                  <CardTitle className="flex items-center gap-2">
                    <PieChart className="h-4 w-4" />
                    {pattern.patternType.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())}
                  </CardTitle>
                  <CardDescription>{pattern.description}</CardDescription>
                </CardHeader>
                <CardContent>
                  <div className="space-y-2">
                    {Object.entries(pattern.data).map(([key, value]) => (
                      <div key={key} className="flex justify-between">
                        <span className="text-sm">{key}</span>
                        <div className="flex items-center gap-2">
                          <Progress value={(value as number) / 30 * 100} className="w-20" />
                          <span className="text-sm font-medium">{value}</span>
                        </div>
                      </div>
                    ))}
                  </div>
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
