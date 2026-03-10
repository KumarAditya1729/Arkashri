'use client'

import { useState, useEffect } from 'react'
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Progress } from '@/components/ui/progress'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { 
  Activity, 
  Cpu, 
  HardDrive, 
  MemoryStick, 
  Network, 
  AlertTriangle, 
  CheckCircle, 
  TrendingUp, 
  TrendingDown,
  Server,
  Zap,
  Clock,
  Users,
  BarChart3,
  PieChart
} from 'lucide-react'
import {
  LineChart,
  Line,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer
} from 'recharts'

interface MetricData {
  timestamp: string
  cpu: number
  memory: number
  disk: number
  network: number
  requests: number
  errors: number
}

interface PodStatus {
  name: string
  status: 'running' | 'pending' | 'failed'
  cpu: number
  memory: number
  restarts: number
  age: string
}

interface ServiceHealth {
  name: string
  status: 'healthy' | 'unhealthy' | 'degraded'
  responseTime: number
  uptime: number
  lastCheck: string
}

export default function MonitoringPage() {
  const [metrics, setMetrics] = useState<MetricData[]>([])
  const [pods, setPods] = useState<PodStatus[]>([])
  const [services, setServices] = useState<ServiceHealth[]>([])
  const [loading, setLoading] = useState(true)
  const [selectedTimeRange, setSelectedTimeRange] = useState('1h')

  useEffect(() => {
    fetchMonitoringData()
    const interval = setInterval(fetchMonitoringData, 30000) // Refresh every 30 seconds
    return () => clearInterval(interval)
  }, [selectedTimeRange])

  const fetchMonitoringData = async () => {
    try {
      setLoading(true)
      
      // Mock metrics data - in production, fetch from Prometheus/Grafana
      const now = new Date()
      const mockMetrics: MetricData[] = Array.from({ length: 60 }, (_, i) => ({
        timestamp: new Date(now.getTime() - (59 - i) * 60000).toISOString(),
        cpu: Math.random() * 40 + 30,
        memory: Math.random() * 30 + 50,
        disk: Math.random() * 20 + 40,
        network: Math.random() * 100 + 50,
        requests: Math.floor(Math.random() * 500 + 200),
        errors: Math.floor(Math.random() * 10)
      }))

      const mockPods: PodStatus[] = [
        {
          name: 'arkashri-api-1',
          status: 'running',
          cpu: 45,
          memory: 65,
          restarts: 0,
          age: '2d 5h'
        },
        {
          name: 'arkashri-api-2',
          status: 'running',
          cpu: 38,
          memory: 58,
          restarts: 1,
          age: '2d 5h'
        },
        {
          name: 'arkashri-api-3',
          status: 'running',
          cpu: 52,
          memory: 72,
          restarts: 0,
          age: '2d 5h'
        },
        {
          name: 'arkashri-worker-1',
          status: 'running',
          cpu: 25,
          memory: 40,
          restarts: 0,
          age: '2d 5h'
        },
        {
          name: 'prometheus',
          status: 'running',
          cpu: 15,
          memory: 30,
          restarts: 0,
          age: '5d 12h'
        },
        {
          name: 'grafana',
          status: 'running',
          cpu: 10,
          memory: 25,
          restarts: 0,
          age: '5d 12h'
        }
      ]

      const mockServices: ServiceHealth[] = [
        {
          name: 'API Service',
          status: 'healthy',
          responseTime: 145,
          uptime: 99.9,
          lastCheck: new Date().toISOString()
        },
        {
          name: 'Database',
          status: 'healthy',
          responseTime: 25,
          uptime: 99.8,
          lastCheck: new Date().toISOString()
        },
        {
          name: 'Redis Cache',
          status: 'healthy',
          responseTime: 5,
          uptime: 100,
          lastCheck: new Date().toISOString()
        },
        {
          name: 'Blockchain Service',
          status: 'degraded',
          responseTime: 2500,
          uptime: 95.5,
          lastCheck: new Date().toISOString()
        }
      ]

      setMetrics(mockMetrics)
      setPods(mockPods)
      setServices(mockServices)
    } catch (error) {
      console.error('Failed to fetch monitoring data:', error)
    } finally {
      setLoading(false)
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'running':
        return 'bg-green-500'
      case 'degraded':
      case 'pending':
        return 'bg-yellow-500'
      case 'unhealthy':
      case 'failed':
        return 'bg-red-500'
      default:
        return 'bg-gray-500'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
      case 'running':
        return <CheckCircle className="h-4 w-4" />
      case 'degraded':
      case 'pending':
        return <AlertTriangle className="h-4 w-4" />
      case 'unhealthy':
      case 'failed':
        return <AlertTriangle className="h-4 w-4" />
      default:
        return <Activity className="h-4 w-4" />
    }
  }

  const currentMetrics = metrics[metrics.length - 1] || {
    cpu: 0,
    memory: 0,
    disk: 0,
    network: 0,
    requests: 0,
    errors: 0
  }

  return (
    <div className="container mx-auto p-6 space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight">Production Monitoring</h1>
          <p className="text-muted-foreground">
            Real-time monitoring and observability for Arkashri infrastructure
          </p>
        </div>
        <div className="flex gap-2">
          <select
            value={selectedTimeRange}
            onChange={(e) => setSelectedTimeRange(e.target.value)}
            className="px-3 py-2 border rounded-md"
          >
            <option value="1h">Last Hour</option>
            <option value="6h">Last 6 Hours</option>
            <option value="24h">Last 24 Hours</option>
            <option value="7d">Last 7 Days</option>
          </select>
          <Button variant="outline" size="sm">
            <BarChart3 className="mr-2 h-4 w-4" />
            Grafana Dashboard
          </Button>
        </div>
      </div>

      <Tabs defaultValue="overview" className="space-y-4">
        <TabsList className="grid w-full grid-cols-4">
          <TabsTrigger value="overview">Overview</TabsTrigger>
          <TabsTrigger value="pods">Pods</TabsTrigger>
          <TabsTrigger value="services">Services</TabsTrigger>
          <TabsTrigger value="metrics">Metrics</TabsTrigger>
        </TabsList>

        <TabsContent value="overview" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">CPU Usage</CardTitle>
                <Cpu className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{currentMetrics.cpu.toFixed(1)}%</div>
                <Progress value={currentMetrics.cpu} className="mt-2" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Memory Usage</CardTitle>
                <MemoryStick className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{currentMetrics.memory.toFixed(1)}%</div>
                <Progress value={currentMetrics.memory} className="mt-2" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Disk Usage</CardTitle>
                <HardDrive className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{currentMetrics.disk.toFixed(1)}%</div>
                <Progress value={currentMetrics.disk} className="mt-2" />
              </CardContent>
            </Card>

            <Card>
              <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
                <CardTitle className="text-sm font-medium">Network I/O</CardTitle>
                <Network className="h-4 w-4 text-muted-foreground" />
              </CardHeader>
              <CardContent>
                <div className="text-2xl font-bold">{currentMetrics.network.toFixed(0)} MB/s</div>
                <div className="flex items-center mt-2 text-sm text-muted-foreground">
                  <TrendingUp className="h-3 w-3 mr-1" />
                  +12% from last hour
                </div>
              </CardContent>
            </Card>
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Request Rate</CardTitle>
                <CardDescription>API requests per minute</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <AreaChart data={metrics.slice(-20)}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" />
                    <YAxis />
                    <Tooltip />
                    <Area type="monotone" dataKey="requests" stroke="#8884d8" fill="#8884d8" fillOpacity={0.6} />
                  </AreaChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Error Rate</CardTitle>
                <CardDescription>Errors per minute</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={200}>
                  <LineChart data={metrics.slice(-20)}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" />
                    <YAxis />
                    <Tooltip />
                    <Line type="monotone" dataKey="errors" stroke="#FF4444" strokeWidth={2} />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="pods" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Pod Status</CardTitle>
              <CardDescription>Kubernetes pod health and resource usage</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {pods.map((pod, index) => (
                  <div key={index} className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="flex items-center space-x-4">
                      <div className={`w-3 h-3 rounded-full ${getStatusColor(pod.status)}`} />
                      <div>
                        <p className="font-medium">{pod.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {pod.age} • {pod.restarts} restarts
                        </p>
                      </div>
                    </div>
                    <div className="text-right space-y-1">
                      <div className="flex items-center text-sm">
                        <Cpu className="h-3 w-3 mr-1" />
                        {pod.cpu}%
                      </div>
                      <div className="flex items-center text-sm">
                        <MemoryStick className="h-3 w-3 mr-1" />
                        {pod.memory}%
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="services" className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Service Health</CardTitle>
              <CardDescription>Application service status and performance</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="space-y-4">
                {services.map((service, index) => (
                  <div key={index} className="flex items-center justify-between p-4 border rounded-lg">
                    <div className="flex items-center space-x-4">
                      <div className={`w-3 h-3 rounded-full ${getStatusColor(service.status)}`} />
                      <div>
                        <p className="font-medium">{service.name}</p>
                        <p className="text-sm text-muted-foreground">
                          {service.lastCheck}
                        </p>
                      </div>
                    </div>
                    <div className="text-right space-y-1">
                      <Badge variant={service.status === 'healthy' ? 'default' : 'destructive'}>
                        {service.status}
                      </Badge>
                      <div className="text-sm">
                        <Zap className="h-3 w-3 mr-1 inline" />
                        {service.responseTime}ms
                      </div>
                      <div className="text-sm text-muted-foreground">
                        {service.uptime}% uptime
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="metrics" className="space-y-4">
          <div className="grid gap-4 md:grid-cols-2">
            <Card>
              <CardHeader>
                <CardTitle>Resource Usage Trends</CardTitle>
                <CardDescription>CPU and Memory utilization</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <LineChart data={metrics}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Line type="monotone" dataKey="cpu" stroke="#8884d8" name="CPU %" />
                    <Line type="monotone" dataKey="memory" stroke="#82ca9d" name="Memory %" />
                  </LineChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle>Network & Disk I/O</CardTitle>
                <CardDescription>System resource utilization</CardDescription>
              </CardHeader>
              <CardContent>
                <ResponsiveContainer width="100%" height={300}>
                  <BarChart data={metrics}>
                    <CartesianGrid strokeDasharray="3 3" />
                    <XAxis dataKey="timestamp" />
                    <YAxis />
                    <Tooltip />
                    <Legend />
                    <Bar dataKey="network" fill="#8884d8" name="Network (MB/s)" />
                    <Bar dataKey="disk" fill="#82ca9d" name="Disk (%)" />
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          </div>
        </TabsContent>
      </Tabs>
    </div>
  )
}
