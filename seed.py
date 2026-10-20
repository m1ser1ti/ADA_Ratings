from extensions import db
from models import School, Professor


def seed():
    schools = [
        School(code='SPIA', name='School of Public and International Affairs'),
        School(code='SITE', name='School of IT and Engineering'),
        School(code='SB',   name='School of Business'),
        School(code='LAW',  name='School of Law'),
        School(code='SAFS', name='School of Agricultural and Food Sciences'),
        School(code='SDA',  name='School of Design and Architecture'),
        School(code='SE',   name='School of Education'),
        School(code='EAPP', name='English for Academic and Professional Purposes'),
        School(code='FP',   name='Foundation Program'),
    ]
    db.session.add_all(schools)
    db.session.commit()

    spia = School.query.filter_by(code='SPIA').first()
    site = School.query.filter_by(code='SITE').first()
    sb = School.query.filter_by(code='SB').first()
    law = School.query.filter_by(code='LAW').first()
    safs = School.query.filter_by(code='SAFS').first()
    sda = School.query.filter_by(code='SDA').first()

    # SPIA
    spia_professors = [
        Professor(name='Azer Babayev',               title='Dean, Associate Professor',         specialization='Political Science',          profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/1-azer-babayev',           school_id=spia.id),
        Professor(name='Orkhan Nadirov',             title='Associate Dean, Assistant Professor',specialization='Academic Affairs',           profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/9-orkhan-nadirov',          school_id=spia.id),
        Professor(name='Anar Valiyev',               title='Associate Professor',                specialization='Public Administration',       profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/2-anar-valiyev',            school_id=spia.id),
        Professor(name='Ferit Murat Ozkaleli',       title='Associate Professor',                specialization='International Affairs',       profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/3-ferit-murat-ozkaleli',    school_id=spia.id),
        Professor(name='Kavus Abushov',              title='Associate Professor',                specialization='Political Science',           profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/4-kavus-abushov',           school_id=spia.id),
        Professor(name='Sarvar Gurbanov',            title='Associate Professor',                specialization='Economics',                  profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/10-sarvar-gurbanov',         school_id=spia.id),
        Professor(name='Umut Ozkaleli',              title='Associate Professor',                specialization='Sociology',                  profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/5-umut-ozkaleli',           school_id=spia.id),
        Professor(name='Ali Saqer',                  title='Assistant Professor',                specialization='International Affairs',       profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/7-ali-saqer',               school_id=spia.id),
        Professor(name='Amin Babazade',              title='Assistant Professor',                specialization='Economics',                  profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/364-amin-babazade',          school_id=spia.id),
        Professor(name='Daniel Pommier Vincelli',    title='Assistant Professor',                specialization='International Relations',     profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/6-daniel-pommier-vincelli', school_id=spia.id),
        Professor(name='Farkhad Aliyev',             title='Assistant Professor',                specialization='Political Science',           profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/363-farkhad-aliyev',         school_id=spia.id),
        Professor(name='Lala Jumayeva',              title='Assistant Professor',                specialization='International Affairs',       profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/8-lala-jumayeva',            school_id=spia.id),
        Professor(name='Vener Garayev',              title='Assistant Professor',                specialization='Public Administration',       profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/11-vener-garayev',           school_id=spia.id),
        Professor(name='Damjan Krnjevic Miskovic',   title='Professor of Practice',              specialization='Policy Research',            profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/12-damjan-krnjevic-miskovic',school_id=spia.id),
        Professor(name='Fariz Ismailzade',           title='Professor of Practice',              specialization='International Affairs',       profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/393-fariz-ismailzade',        school_id=spia.id),
        Professor(name='Gulsabah Amirova',           title='Senior Instructor',                  specialization='Communication',              profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/365-gulsabah-amirova',        school_id=spia.id),
        Professor(name='Nargiz Heydarova',           title='Instructor',                         specialization='Economics',                  profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/19-nargiz-heydarova',         school_id=spia.id),
        Professor(name='Vusal Mammadrzayev',         title='Senior Instructor',                  specialization='Decision Sciences',          profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/15-vusal-mammadrzayev',       school_id=spia.id),
        Professor(name='Yuliya Aliyeva-Gureyeva',    title='Instructor',                         specialization='Social Sciences',            profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/20-yuliya-aliyeva-gureyeva', school_id=spia.id),
        Professor(name='Neda Salahshour',            title='Assistant Professor',                specialization='Communication',              profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/486-neda-salahshour',         school_id=spia.id),
        Professor(name='Bairam Akhundov',            title='Instructor',                         specialization='Public Administration',       profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/379-bairam-akhundov',         school_id=spia.id),
        Professor(name='Zhanat Alimanov',            title='Assistant Professor',                specialization='Law',                        profile_url='https://www.ada.edu.az/en/schools/spia/members/faculty/490-zhanat-alimanov',         school_id=spia.id),
    ]
    db.session.add_all(spia_professors)
    db.session.commit()

    # SITE
    site_professors = [
        Professor(name='Abzatdin Adamov',    title='Dean, Professor',                                    specialization='Big Data Analytics',             profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/55-abzatdin-adamov',    school_id=site.id),
        Professor(name='Vugar Musayev',      title='Assistant Professor, Associate Dean',                specialization='Mathematics and Statistics',     profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/67-vugar-musayev',      school_id=site.id),
        Professor(name='Jamaladdin Hasanov', title='Associate Professor, Director of BSIT Program',     specialization='Computer and Information Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/63-jamaladdin-hasanov', school_id=site.id),
        Professor(name='Samir Rustamov',     title='Associate Professor, Director of BSCS Program',     specialization='Computer and Information Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/57-samir-rustamov',     school_id=site.id),
        Professor(name='Wisam Al-Dayyeni',   title='Assistant Professor, Program Director CE & EEE',    specialization='Electrical Engineering',         profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/70-wisam-al-dayyeni',   school_id=site.id),
        Professor(name='Yagub Aliyev',       title='Associate Professor, Program Director Mathematics', specialization='Mathematics and Statistics',     profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/68-yagub-aliyev',       school_id=site.id),
        Professor(name='Araz Yusubov',       title='Assistant Professor',                               specialization='Computer and Information Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/58-araz-yusubov',       school_id=site.id),
        Professor(name='Burcu Ramazanli',    title='Assistant Professor',                               specialization='Engineering',                    profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/59-burcu-ramazanli',    school_id=site.id),
        Professor(name='Elchin Hasanalizade',title='Assistant Professor',                               specialization='Mathematics',                    profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/60-elchin-hasanalizade',school_id=site.id),
        Professor(name='Fuad Hajiyev',       title='Assistant Professor',                               specialization='Mathematics',                    profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/61-fuad-hajiyev',       school_id=site.id),
        Professor(name='Gulmammad Mammadov', title='Assistant Professor',                               specialization='Physics',                        profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/62-gulmammad-mammadov', school_id=site.id),
        Professor(name='Javanshir Azizov',   title='Assistant Professor',                               specialization='Mathematics',                    profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/73-javanshir-azizov',   school_id=site.id),
        Professor(name='John Thomas Burns',  title='Assistant Professor',                               specialization='Computer and Information Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/375-john-thomas-burns', school_id=site.id),
        Professor(name='Mykhailo Medvediev', title='Assistant Professor',                               specialization='Computer and Information Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/64-mykhailo-medvediev', school_id=site.id),
        Professor(name='Orkhan Karimzada',   title='Assistant Professor',                               specialization='Electrical Engineering',         profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/66-orkhan-karimzada',   school_id=site.id),
        Professor(name='Rashad Aliyev',      title='Assistant Professor',                               specialization='Computer and Information Science',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/372-rashad-aliyev',    school_id=site.id),
        Professor(name='Samin Malik',        title='Assistant Professor',                               specialization='Mathematics',                    profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/65-samin-malik',        school_id=site.id),
        Professor(name='Rafail Alizade',     title='Associate Professor',                               specialization='Mathematics',                    profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/56-rafail-alizade',     school_id=site.id),
        Professor(name='Ismayil Shahaliyev', title='Instructor',                                        specialization='Information and Computer Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/72-ismayil-shahaliyev', school_id=site.id),
        Professor(name='Nuraddin Sadili',    title='Senior Instructor',                                 specialization='Computer and Information Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/76-nuraddin-sadili',    school_id=site.id),
        Professor(name='Orkhan Mammadov',    title='Instructor',                                        specialization='Computer and Information Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/373-orkhan-mammadov',   school_id=site.id),
        Professor(name='Pasha Pashazade',    title='Instructor',                                        specialization='Computer Engineering',            profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/77-pasha-pashazade',    school_id=site.id),
        Professor(name='Samir Mammadov',     title='Instructor',                                        specialization='Computer and Information Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/78-samir-mammadov',     school_id=site.id),
        Professor(name='Ruslan Muslumov',    title='Assistant Professor',                               specialization='Mathematics',                    profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/469-ruslan-muslumov',   school_id=site.id),
        Professor(name='Said Pashayev',      title='Assistant Professor',                               specialization='Physics',                        profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/480-said-pashayev',     school_id=site.id),
        Professor(name='Natig Atakishiyev',  title='Professor',                                         specialization='Mathematics',                    profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/481-natig-atakishiyev', school_id=site.id),
        Professor(name='Alexz Farrall',      title='Assistant Professor',                               specialization='Computer Engineering',            profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/483-alexz-farrall',     school_id=site.id),
        Professor(name='Azar Aliyev',        title='Instructor',                                        specialization='Computer and Information Sciences',profile_url='https://www.ada.edu.az/en/schools/site/members/faculty/484-azar-aliyev',       school_id=site.id),
    ]
    db.session.add_all(site_professors)
    db.session.commit()

    # SB
    sb_professors = [
        Professor(name='Huseyn Ismayilov',   title='Dean, School of Business',           specialization='School of Business',           profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Ruslan Aliyev',      title='Associate Dean, Academic Affairs',   specialization='Economics',                    profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Elkin Nurmammadov',  title='Vice Rector, Academic Affairs',      specialization='Economics',                    profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Ali Gunesh',         title='Associate Professor',                specialization='Economics',                    profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Aysel Bandad',       title='Senior Instructor',                  specialization='Economics',                    profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Azar Abizada',       title='Professor',                          specialization='Economics',                    profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Azra Brankovic',     title='Visiting Professor',                 specialization='International Business',        profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Elnur Eyvazov',      title='Lead Instructor',                    specialization='Legal Professions and Studies',profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Emin Ilyas',         title='Senior Instructor',                  specialization='Operations Management',        profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Farid Gadirli',      title='Assistant Professor',                specialization='Finance',                      profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Farkhad Huseynov',   title='Professor',                          specialization='Mathematics and Economics',    profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Fuzuli Aliyev',      title='Assistant Professor',                specialization='Finance',                      profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Hayfaa Tlaiss',      title='Professor',                          specialization='Management',                   profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Hulisi Ogut',        title='Visiting Professor',                 specialization='Information Systems',          profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Ismayil Jafarov',    title='Senior Instructor',                  specialization='Mathematics and Statistics',   profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Kerim Keskin',       title='Associate Professor',                specialization='Economics',                    profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Mehriban Ahmadova',  title='Instructor',                         specialization='Accounting',                   profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Mugabil Isayev',     title='Assistant Professor',                specialization='Finance',                      profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Muharrem Yesilirmak',title='Associate Professor',                specialization='Economics',                    profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Narmina Rustamova',  title='Instructor',                         specialization='Economics',                    profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Omar Farooq',        title='Professor',                          specialization='Finance and Financial Management',profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Samir Orujov',       title='Assistant Professor',                specialization='Mathematics and Statistics',   profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
        Professor(name='Zaur Abdullazade',   title='Instructor',                         specialization='Accounting',                   profile_url='https://www.ada.edu.az/en/schools/sb', school_id=sb.id),
    ]
    db.session.add_all(sb_professors)
    db.session.commit()

    # LAW
    law_professors = [
        Professor(name='Rashad Ibadov',                title='Dean',                                specialization='School of Law',   profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Javid Gadirov',                title='Associate Dean, Assistant Professor', specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Azad Talibov',                 title='Associate Professor',                 specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Farid Ahmadov',                title='Associate Professor',                 specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Anar Jafarov',                 title='Assistant Professor',                 specialization='Philosophy',      profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Aynur Akhundli',               title='Assistant Professor',                 specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Kamala Nazarova',              title='Assistant Professor',                 specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Altay Mustafayev',             title='Professor of Practice',               specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Juan Rodrigo Labardini Flores',title='Professor of Practice',               specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Emin Karimov',                 title='Professor of Practice',               specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Abiddin Huseynov',             title='Adjunct Professor of Legal Practice', specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Justice Khagani Mammadov',     title='Adjunct Professor of Legal Practice', specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Mahir Abbasov',                title='Adjunct Lecturer',                    specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Zaur Naghiyev',                title='Adjunct Lecturer',                    specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Elnur Karimov',                title='Assistant Professor',                 specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Tabriz Jafarov',               title='Assistant Professor',                 specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Dunyamin Novruzov',            title='Assistant Professor',                 specialization='Law',             profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
        Professor(name='Shahlar Mammadov',             title='Professor',                           specialization='Practice in Law', profile_url='https://www.ada.edu.az/en/schools/law', school_id=law.id),
    ]
    db.session.add_all(law_professors)
    db.session.commit()

    # SAFS
    safs_professors = [
        Professor(name='Matteo Vittuari',  title='Dean',                specialization='Agricultural and Food Policy', profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='Saida Aliyeva',    title='Assistant Professor', specialization='Food Sciences',               profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='Asaf Omarov',      title='Assistant Professor', specialization='Animal Sciences',             profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='Madina Guliyeva',  title='Assistant Professor', specialization='Food Sciences',               profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='Sahil Guliyev',    title='Assistant Professor', specialization='Agricultural Sciences',       profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='Mehraj Abbasov',   title='Assistant Professor', specialization='Agricultural Sciences',       profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='Matilde Tura',     title='Visiting Professor',  specialization='Food Sciences',               profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='Marcello Russo',   title='Visiting Professor',  specialization='Agricultural Sciences',       profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='Giacomo Zanello',  title='Visiting Professor',  specialization='Agricultural Sciences',       profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='Cesare Zanasi',    title='Visiting Professor',  specialization='Agricultural Sciences',       profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
        Professor(name='William H. Meyers',title='Visiting Professor',  specialization='Agricultural Economics',      profile_url='https://www.ada.edu.az/en/schools/safs', school_id=safs.id),
    ]
    db.session.add_all(safs_professors)
    db.session.commit()

    # SDA
    sda_professors = [
        Professor(name='Silvia Ferraris',         title='Dean, School of Design & Architecture', specialization='Design',                       profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Marco Bovati',            title='Associate Dean',                        specialization='Architectural and Urban Design',profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Nora Lombardini',         title='Associate Dean',                        specialization='Architectural Conservation',    profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Emir Huseynov',           title='Assistant Professor',                   specialization='Architecture',                  profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Leyla Hasanova',          title='Assistant Professor',                   specialization='Architectural Design',          profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Carl Haddrell',           title='Assistant Professor',                   specialization='Design',                       profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Stefania Sini',           title='Visiting Assistant Professor',          specialization='Architecture and Design',       profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Melania Vicentini',       title='Visiting Assistant Professor',          specialization='Design',                       profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Ermes Invernizzi',        title='Visiting Assistant Professor',          specialization='Architecture',                  profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Dina Jovanovic Lombardo', title='Visiting Assistant Professor',          specialization='Architecture and Design',       profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Angel Cordero Ampuero',   title='Visiting Associate Professor',          specialization='Architecture',                  profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Deniz Ozge Aytac',        title='Assistant Professor',                   specialization='Interior Design',               profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Nigar Aghayeva',          title='Adjunct Instructor of Mathematics',     specialization='Architecture',                  profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
        Professor(name='Lala Guluzada',           title='Assistant Professor',                   specialization='Design',                       profile_url='https://www.ada.edu.az/en/schools/sda', school_id=sda.id),
    ]
    db.session.add_all(sda_professors)
    db.session.commit()

    print(f"Seeded: {School.query.count()} schools, {Professor.query.count()} professors")