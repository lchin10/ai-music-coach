# AI Music Coach (in progress)

AI Music Coach is a web application designed to help musicians (especially pianists) practice more effectively through structured, AI-assisted practice planning. Users can upload sheet music PDFs, and the app analyzes the score using computer vision and music theory heuristics to generate personalized practice recommendations, section breakdowns, and targeted drills.

I built this project as someone who has played piano for ~15 years and minored in music performance. Outside of software, music has always been one of my favorite hobbies, and I wanted to create something for people who still want to grow as musicians even when music is no longer their full-time focus. The goal is to make practicing feel more organized, motivating, and sustainable for hobbyists and serious learners alike.

The app serves as both a practice planner and a progress tracker, allowing users to resume sessions seamlessly and build long-term consistency through data-driven insights.

## Features

### MVP Features
- **Sheet Music Upload**: Upload piano sheet music in PDF format.
- **Computer Vision-Based Score Detection**: Uses OpenCV-based music notation detection to validate and analyze uploaded sheet music
- **AI-Powered Analysis**: Automatically generates:
  - Section breakdowns
  - Tempo suggestions
  - Targeted drills (e.g., hands-separate practice, specific measure focus)
- **Practice Tracker**: Tracks time spent practicing and sections worked on.
- **Progress Memory**: Resume practice sessions without losing progress.

### Planned Features
- **Real-Time Feedback**: Microphone integration for live feedback on timing, notes, and technique.
- **Adaptive Practice Plans**: Dynamic recommendations that evolve based on user progress and weaknesses.
- **Difficulty Heatmaps**: Visual indicators of technically difficult sections.
- **Pattern Detection**: Detection of musical patterns (scales, arpeggios, jumps, polyrhythms) for tailored advice.
- **Library of Pieces**: Pre-built plans for popular piano pieces.

## Workflow

1. **Upload Sheet Music**: Upload a PDF containing piano sheet music.
2. **Score Analysis**: The backend analyzes the document using OpenCV-based notation detection and music analysis heuristics.
3. **Practice Plan Generation**: Receive a customized lesson plan with sections, tempo recommendations, and specific drills (e.g., "Practice measures 12–20 with left-hand jumps at 60 BPM").
4. **Practice Session**: Start a session, work through the plan, and track your progress.
5. **Resume Anytime**: Stop and restart sessions without losing progress.

## Technology Stack

- **Frontend**: Next.js, React, Typescript
- **Backend**: Next.js API, FastAPI, Python
- **Computer Vision / Music Analysis**: OpenCV, PyMuPDF, NumPy, Pillow
- **Deployment**: Vercel (frontend), Docker (backend)

## Requirements

- Node.js 18+
- Python 3.10+
- npm or yarn for package management
- A modern web browser with JavaScript enabled

## Installation and Setup

**Clone the Repository**:
  ```bash
  git clone https://github.com/yourusername/ai-music-coach.git
  cd ai-music-coach
  ```

**Frontend Setup**:
  Navigate to the frontend directory and install packages:
  ```bash
  cd frontend
  npm install
  npm run dev
  ```
  Frontend runs at [http://localhost:3000](http://localhost:3000)

**Backend Setup**:
  ```bash
  cd backend
  make install
  make run
  ```
  Backend runs at [http://localhost:8000/docs](http://localhost:8000/docs)

4. **Build for Production**:
   ```bash
   npm run build
   npm start
   ```

## Future Development

- More robust music notation detection
- Better section segmentation
- AI-generated fingering suggestions
- Real-time performance feedback
- Cloud-based accounts and sync
- Mobile support
- Expanded support for non-piano instruments