from flask import Flask, render_template, request, redirect, url_for, current_app
from flask_basicauth import BasicAuth
import praw
from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.jobstores.sqlalchemy import SQLAlchemyJobStore

app = Flask(__name__)
app.config['BASIC_AUTH_USERNAME'] = 'admin123'
app.config['BASIC_AUTH_PASSWORD'] = 'jplank'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///reddit.db'
app.config['SCHEDULER_JOBSTORES'] = {
    'default': SQLAlchemyJobStore(url='sqlite:///jobs.db')
}
app.config['SCHEDULER_API_ENABLED'] = True

db = SQLAlchemy(app)
basic_auth = BasicAuth(app)

reddit_client_id = 'k_JFwKhEUKPg9uXbLcFrKg'
reddit_client_secret = 'ZtvCMdYnDYAASz_XJwbOTop_UO3chw'
reddit_user_agent = 'subsearch by u/enadev'

reddit = praw.Reddit(
    client_id=reddit_client_id,
    client_secret=reddit_client_secret,
    user_agent=reddit_user_agent
)

scheduler = BackgroundScheduler(jobstores=app.config['SCHEDULER_JOBSTORES'])
scheduler.start()

class Post(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.String(20), nullable=False)
    subreddit = db.Column(db.String(50), nullable=False)
    karma = db.Column(db.Integer, nullable=False)
    username = db.Column(db.String(50), nullable=False)
    tags = db.Column(db.String(50))
    title = db.Column(db.String(255), nullable=False)
    url = db.Column(db.String(255), nullable=False, unique=True)

with app.app_context():
    db.create_all()

admin_subreddits = []

def fetch_latest_content(subreddit_name):
    with app.app_context():
        print(f"Fetching latest content for {subreddit_name}...")
        num_posts_per_subreddit = 1000

        try:
            subreddit = reddit.subreddit(subreddit_name)
            new_posts = subreddit.new(limit=num_posts_per_subreddit)

            results = []
            for post in new_posts:
                post_info = Post(
                    date=datetime.utcfromtimestamp(post.created_utc).strftime('%Y-%m-%d %H:%M:%S'),
                    subreddit=post.subreddit.display_name,
                    karma=post.score,
                    username=str(post.author),
                    tags=post.link_flair_text,
                    title=post.title,
                    url=post.url
                )

                if not Post.query.filter_by(url=post_info.url).first():
                    db.session.add(post_info)
                    results.append(post_info)

            db.session.commit()

        except Exception as e:
            print(f"An error occurred: {e}")

        print(f"Fetching for {subreddit_name} completed.")

def fetch_and_update_subreddit(subreddit_name):
    with app.app_context():
        print(f"Running fetch_and_update_subreddit for {subreddit_name} at {datetime.now()}")
        fetch_latest_content(subreddit_name)

@app.route('/add_subreddit', methods=['POST'])
@basic_auth.required
def add_subreddit():
    new_subreddit = request.form.get('subreddit')
    if new_subreddit not in admin_subreddits:
        admin_subreddits.append(new_subreddit)
        fetch_latest_content(new_subreddit)  # Fetch content immediately
        scheduler.add_job(fetch_and_update_subreddit, 'interval', minutes=30, args=[new_subreddit], id=f'fetch_and_update_subreddit_{new_subreddit}')  # Schedule periodic update
    return redirect(url_for('admin_panel'))  # Use url_for to generate the URL of the 'admin_panel' route

@app.route('/remove_subreddit', methods=['POST'])
@basic_auth.required
def remove_subreddit():
    subreddit_to_remove = request.form.get('remove_subreddit')
    if subreddit_to_remove in admin_subreddits:
        admin_subreddits.remove(subreddit_to_remove)

        # Eliminar tarea programada
        job_id = f'fetch_and_update_subreddit_{subreddit_to_remove}'
        scheduler.remove_job(job_id)

        # Eliminar posts correspondientes al subreddit eliminado de la base de datos
        posts_to_remove = Post.query.filter_by(subreddit=subreddit_to_remove).all()
        for post in posts_to_remove:
            db.session.delete(post)

        db.session.commit()

    return redirect(url_for('admin_panel'))


@app.route('/search', methods=['POST'])
def search():
    keyword = request.form.get('keyword', '').lower()
    filtered_posts = Post.query.filter(Post.title.ilike(f"%{keyword}%")).all()
    return render_template('index.html', posts=filtered_posts, keyword=keyword)

@app.route('/')
def index():
    posts = Post.query.order_by(Post.date.desc()).all()
    return render_template('index.html', posts=posts)

@app.route('/admin', methods=['GET', 'POST'])
@basic_auth.required
def admin_panel():
    return render_template('admin.html', admin_subreddits=admin_subreddits)

if __name__ == '__main__':
    app.run(debug=True)