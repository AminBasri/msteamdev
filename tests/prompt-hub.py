from openlit import openlit

response = openlit.get_prompt(
  url="http://10.10.6.243:3000", 
  api_key="openlit-DbziPvFb1dPhtYPYpthg+78Udxn0NAxqlOgyY4FzcdQ=",  
  name="recommend_actions_description",
  should_compile=True,                
  variables={
    "title": "Amin",            
  },
)

print(response)